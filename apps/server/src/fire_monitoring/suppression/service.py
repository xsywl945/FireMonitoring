from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
from fire_monitoring_inference.suppression.kinematics import GimbalParams
from fire_monitoring_inference.suppression.machine import MachineConfig, RoomMachine, Shot
from fire_monitoring_inference.suppression.voice import MemorySpeaker

from ..alerts.service import record_event
from ..models import Room


def _local_fire(alert_type: str, observations: list[dict], pump) -> bool:
    if alert_type not in {"FIRE", "FIRE_AND_SMOKE"}:
        return False
    return any(
        item["class_name"] == "fire"
        and item["score"] >= pump.config.local_min_confidence
        and item["effective_frames"] >= pump.config.local_min_frames
        for item in observations
    )


def _grade(analysis: dict | None) -> str:
    if analysis is None:
        return "待判"
    return analysis["level"]["grade"]


def _size(room: Room, settings) -> tuple[float, float]:
    if room.floor_plan_json:
        data = json.loads(room.floor_plan_json)
        size = data.get("size_m")
        if size is not None:
            return float(size[0]), float(size[1])
    return settings.room_width_m, settings.room_depth_m


class SuppressionService:
    def __init__(self, config, session_factory, pump, events, *, panel=None, speaker=None, clock=None) -> None:
        self.config = config
        self.session_factory = session_factory
        self.pump = pump
        self.events = events
        self.panel = panel
        self.speaker = speaker or MemorySpeaker()
        self.clock = clock or time.monotonic
        self.web_estop = False
        self.machines: dict[int, RoomMachine] = {}
        self.context: dict[int, dict] = {}
        self._lock = threading.RLock()
        self.gimbal = self._load_gimbal()
        self.speed = config.suppression.speed
        self.drag = config.suppression.drag

    def handle(self, job, analysis: dict | None) -> None:
        if self.pump is None or not job.pump_observations:
            return
        session = self.session_factory()
        try:
            room = session.get(Room, job.room_id)
            if room is None:
                raise RuntimeError(f"room {job.room_id} does not exist")
            name = room.name
            scene = room.scene_type
            size = _size(room, self.config.suppression)
        finally:
            session.close()
        with self._lock:
            self.context[job.room_id] = {
                "alert_id": job.alert_id,
                "room_name": name,
                "scene": scene,
                "size": size,
                "alert_type": job.alert_type,
                "observations": job.pump_observations,
                "position": job.position,
                "analysis": analysis,
                "captured_at": job.started_at,
                "flame_present": job.alert_type in {"FIRE", "FIRE_AND_SMOKE"},
                "flame_area": None,
                "landing": None,
                "persons": [],
            }
            self._step(job.room_id, manual_spray=False, admin_unlock=False)

    def tick(self, room_id: int, **updates) -> None:
        with self._lock:
            context = self.context[room_id]
            for key, value in updates.items():
                context[key] = value
            self._step(room_id, manual_spray=False, admin_unlock=False)

    def estop(self) -> dict:
        with self._lock:
            self.web_estop = True
            if self.pump is not None and self.pump.config.enabled:
                self.pump.emergency_stop()
            for room_id in list(self.context):
                self._step(room_id, manual_spray=False, admin_unlock=False)
            return self.snapshot(None)

    def unlock(self) -> dict:
        with self._lock:
            status = self._actuator()
            if status["latch"] == "LATCHED":
                raise RuntimeError("请按下现场复位键")
            if status["latch"] == "ARMED":
                if self.pump.command("UNLOCK") != "UNLOCKED":
                    raise RuntimeError("unlock was rejected")
                status = self._actuator()
            self.web_estop = False
            if self.pump is not None:
                self.pump.release_inhibit()
            for room_id in list(self.context):
                self._step(room_id, manual_spray=False, admin_unlock=True)
            return self.snapshot(None)

    def aim(self, pan_cdeg: int, tilt_cdeg: int) -> dict:
        with self._lock:
            if self.pump is None or not self.pump.config.enabled:
                raise RuntimeError("水泵未启用")
            if self.web_estop:
                raise RuntimeError("系统已急停")
            status = self._actuator()
            if status["latch"] != "CLEAR":
                raise RuntimeError("系统已急停")
            reply = self.pump.command(f"AIM {int(pan_cdeg)} {int(tilt_cdeg)}")
            if not reply.startswith("AIM "):
                raise RuntimeError(reply)
            return self.snapshot(None)

    def manual_spray(self, room_id: int) -> dict:
        with self._lock:
            if room_id not in self.context:
                raise RuntimeError("这个教室还没有火情")
            self._step(room_id, manual_spray=True, admin_unlock=False)
            return self.snapshot(room_id)

    def save_gimbal(self, params: GimbalParams) -> None:
        path = Path(self.config.suppression.gimbal_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(params.to_dict()), encoding="utf-8")
        self.gimbal = params

    def save_drag(self, speed: float, drag: float) -> None:
        self.speed = speed
        self.drag = drag

    def snapshot(self, room_id: int | None) -> dict:
        actuator = self._actuator()
        machine = None if room_id is None else self.machines.get(room_id)
        return {
            "phase": None if machine is None else machine.phase,
            "block": None if machine is None else machine.block,
            "message": _message(machine),
            "cover_probability": None if machine is None else machine.cover_probability,
            "cover_threshold": self.config.suppression.cover_threshold,
            "web_estop": self.web_estop,
            "actuator": actuator,
            "gimbal": self.gimbal.to_dict(),
            "speed": self.speed,
            "drag": self.drag,
        }

    def _load_gimbal(self) -> GimbalParams:
        path = Path(self.config.suppression.gimbal_path)
        if path.is_file():
            return GimbalParams.from_dict(json.loads(path.read_text(encoding="utf-8")))
        settings = self.config.suppression
        return GimbalParams.nominal(
            [settings.gimbal_x, settings.gimbal_y, settings.gimbal_z],
            yaw=float(np.deg2rad(settings.gimbal_yaw_deg)),
            tilt_zero=settings.gimbal_tilt_zero,
        )

    def _machine(self, room_id: int) -> RoomMachine:
        if room_id not in self.machines:
            settings = self.config.suppression
            self.machines[room_id] = RoomMachine(
                MachineConfig(
                    pending_s=settings.pending_seconds,
                    spray_s=self.pump.config.duration_ms / 1000,
                    review_s=settings.review_seconds,
                    clear_s=settings.clear_seconds,
                    max_corrections=settings.max_corrections,
                )
            )
        return self.machines[room_id]

    def _actuator(self) -> dict:
        empty = {
            "pump": "OFF",
            "laser": "OFF",
            "latch": "CLEAR",
            "pan": 0,
            "tilt": 0,
            "heartbeat": False,
        }
        if self.pump is None or not self.pump.config.enabled:
            empty["pump"] = "DISABLED"
            return empty
        try:
            parts = self.pump.command("STATUS").split()
        except Exception:
            return empty
        if len(parts) != 6 or parts[0] != "STATE":
            return empty
        return {
            "pump": parts[1],
            "laser": parts[2],
            "latch": parts[3],
            "pan": int(parts[4]),
            "tilt": int(parts[5]),
            "heartbeat": True,
        }

    def _muted(self) -> bool:
        if self.speaker.muted:
            return True
        if self.panel is None:
            return False
        parts = self.panel.transport.request("STATUS").split()
        return "MUTE" in parts

    def _step(self, room_id: int, *, manual_spray: bool, admin_unlock: bool) -> None:
        context = self.context[room_id]
        actuator = self._actuator()
        captured_at = context["captured_at"]
        if captured_at.tzinfo is None:
            captured_at = captured_at.replace(tzinfo=UTC)
        age = (datetime.now(UTC) - captured_at).total_seconds()
        settings = self.config.suppression
        shot = Shot(
            now=self.clock(),
            room_name=context["room_name"],
            scene=context["scene"],
            local_fire=_local_fire(context["alert_type"], context["observations"], self.pump),
            smoke=context["alert_type"] == "SMOKE",
            analysis=context["analysis"],
            position=context["position"],
            heartbeat_ok=actuator["heartbeat"],
            persons=context["persons"],
            flame_present=context["flame_present"],
            flame_area=context["flame_area"],
            landing=context["landing"],
            web_estop=self.web_estop,
            firmware_latch=actuator["latch"],
            admin_unlock=admin_unlock,
            room_size=context["size"],
            gimbal=self.gimbal,
            speed=self.speed,
            drag=self.drag,
            grade=_grade(context["analysis"]),
            pump_enabled=self.pump.config.enabled,
            zone_ok=self.pump.config.zone_id == room_id,
            evidence_age_s=age,
            max_evidence_age_s=self.pump.config.max_evidence_age_seconds,
            cancelled=False,
            require_vlm=self.pump.config.require_vlm,
            cooldown_elapsed=self._cooldown_elapsed(),
            max_std_m=settings.max_std_m,
            cover_radius_m=settings.cover_radius_m,
            cover_threshold=settings.cover_threshold,
            person_distance_m=settings.person_distance_m,
            manual_spray=manual_spray,
        )
        effects = self._machine(room_id).step(shot)
        self._apply(room_id, context["alert_id"], effects, captured_at)

    def _cooldown_elapsed(self) -> bool:
        seconds = self.pump.config.cooldown_seconds
        if seconds <= 0:
            return True
        now = datetime.now(UTC)
        for record in self.pump.snapshot()["records"]:
            stamp = record.get("attemptedAt")
            if not stamp:
                continue
            moment = datetime.fromisoformat(stamp)
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=UTC)
            if (now - moment).total_seconds() < seconds:
                return False
        return True

    def _apply(self, room_id: int, alert_id: int, effects: list, captured_at: datetime) -> None:
        if not effects:
            return
        session = self.session_factory()
        payloads = []
        try:
            for effect in effects:
                if effect.panel is not None and self.panel is not None:
                    reply = self.panel.transport.request(f"MODE {effect.panel}")
                    if reply != f"MODE {effect.panel}":
                        raise RuntimeError(reply)
                if effect.voice and not self._muted():
                    self.speaker.say(effect.voice)
                if effect.laser is not None and not effect.latch:
                    state = "ON" if effect.laser else "OFF"
                    reply = self.pump.command(f"LASER {state}")
                    if reply != f"LASER {state}":
                        raise RuntimeError(reply)
                if effect.aim is not None and not effect.latch:
                    reply = self.pump.command(f"AIM {effect.aim[0]} {effect.aim[1]}")
                    if not reply.startswith("AIM "):
                        raise RuntimeError(reply)
                if effect.latch:
                    self.pump.emergency_stop()
                elif effect.stop:
                    self.pump.cutoff()
                if effect.run:
                    self.pump.dispatch_run(
                        uuid4().hex,
                        self.pump.config.duration_ms,
                        captured_at=captured_at,
                        zone_id=room_id,
                    )
                detail = {"phase": effect.phase, "voice": effect.voice, **effect.detail}
                payloads.append(
                    record_event(
                        session,
                        room_id=room_id,
                        alert_id=alert_id,
                        kind=effect.kind,
                        detail=detail,
                    )
                )
            session.commit()
        finally:
            session.close()
        for payload in payloads:
            self.events.publish(payload)


def _message(machine: RoomMachine | None) -> str | None:
    if machine is None or machine.block is None:
        return None
    if machine.block == "OUT_OF_RANGE":
        return "超出喷射范围"
    if machine.block == "WATER_PROHIBITED":
        return "禁止用水"
    if machine.block == "PERSON":
        return "附近有人，已停止喷水"
    return machine.block
