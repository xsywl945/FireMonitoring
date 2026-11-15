from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from fire_monitoring_inference.actuator_v2 import ActuatorDevice
from fire_monitoring_inference.panel_v2 import PanelDevice
from fire_monitoring_inference.pump import PumpConfig, PumpController
from fire_monitoring_inference.suppression.ballistics import integrate
from fire_monitoring_inference.suppression.kinematics import GimbalParams
from sqlalchemy import delete, select

from ..alerts.pipeline import AlertPipeline
from ..models import Alert, AlertClip, AlertEvent, AlertFrame, Camera, Disposition, Room, RoomCamera
from ..sms.aliyun import AliyunSmsSender
from ..sms.service import SmsService
from ..suppression.service import SuppressionService
from .hardware import DeviceLink
from .pack import load_pack
from .player import DemoPlayer
from .render import BOARD, CABINET, DESKS


class _Panel:
    def __init__(self, transport: DeviceLink) -> None:
        self.transport = transport

    def close(self) -> None:
        self.transport.close()


class DemoService:
    def __init__(self, config, session_factory, evidence, events, live) -> None:
        self.config = config
        self.pack = load_pack(config.demo.pack)
        self.session_factory = session_factory
        self.evidence = evidence
        self.events = events
        self.live = live
        self.room_id, self.cameras, self.calibrations = self._seed()
        self.pump, self.panel, self._serial = self._hardware()
        self.suppression = SuppressionService(
            config,
            session_factory,
            self.pump,
            events,
            panel=self.panel,
            pump_run=config.demo.pump_run,
        )
        self.player = DemoPlayer(self)
        self.suppression.clock = self.player.clock.monotonic
        self.suppression.moment = self.player.clock.now
        self.suppression.person_source = self.player.persons
        self.pump.clock = self.player.clock.now
        self._apply_gimbal()
        sms = SmsService(config, AliyunSmsSender(config.sms))
        self.pipeline = AlertPipeline(
            config,
            session_factory,
            evidence,
            None,
            sms,
            self.pump,
            events,
            panel=self.panel,
            suppression=self.suppression,
            on_fatal=lambda: None,
        )
        self.pipeline.start()
        if self.panel is not None:
            reply = self.panel.transport.request("MODE GREEN")
            if reply != "MODE GREEN":
                raise RuntimeError(reply)
            self.suppression.alarm = "GREEN"

    def close(self) -> None:
        self.player.stop()
        self.pipeline.stop()
        self.pump.close()
        if self.panel is not None:
            self.panel.close()

    def prepare_script(self, script_id: str | None) -> None:
        self._clear_room()
        self.suppression.machines.clear()
        self.suppression.context.clear()
        self.suppression.web_estop = False
        self.suppression.alarm = "GREEN"
        if not self._serial:
            self.pump.transport.device = ActuatorDevice()
            self.panel.transport.device = PanelDevice()
            self.pump.transport.step_ms = int(round(1000 / self.pack["fps"]))
            self.panel.transport.step_ms = int(round(1000 / self.pack["fps"]))
        if self.panel is not None:
            reply = self.panel.transport.request("MODE GREEN")
            if reply != "MODE GREEN":
                raise RuntimeError(reply)
        self.player.jpegs = {}
        self.player.elapsed_s = 0.0
        if script_id is not None:
            self.player.clock.set(0)

    def status(self) -> dict:
        script_id = self.player.script_id
        script = None if script_id is None else self.pack["scripts"][script_id]
        machine = self.suppression.machines.get(self.room_id)
        session = self.session_factory()
        try:
            alert = session.scalar(
                select(Alert).where(Alert.room_id == self.room_id).order_by(Alert.id.desc()).limit(1)
            )
            analysis = None if alert is None or not alert.analysis_json else json.loads(alert.analysis_json)
            position = None if alert is None or not alert.position_json else json.loads(alert.position_json)
            rows = session.scalars(
                select(AlertEvent).where(AlertEvent.room_id == self.room_id).order_by(AlertEvent.id)
            ).all()
        finally:
            session.close()
        body = self.suppression.snapshot(self.room_id)
        gimbal = self.suppression.gimbal
        pan = body["actuator"]["pan"]
        tilt = body["actuator"]["tilt"]
        body["actuator"]["pan_deg"] = float(np.degrees(gimbal.pan_scale * (pan - gimbal.pan_zero)))
        body["actuator"]["tilt_deg"] = float(np.degrees(gimbal.tilt_scale * (tilt - gimbal.tilt_zero)))
        body.update(
            {
                "enabled": True,
                "label": "演示模式",
                "synthetic": bool(self.pack.get("synthetic")),
                "note": self.pack.get("note", ""),
                "hardware": self.config.demo.hardware,
                "detector": self.config.demo.detector,
                "room_id": self.room_id,
                "room_name": self.pack["room"]["name"],
                "script": script_id,
                "script_title": None if script is None else script["title"],
                "scripts": [
                    {"id": item["id"], "title": item["title"], "duration_s": item["duration_s"]}
                    for item in self.pack["scripts"].values()
                ],
                "running": self.player.running,
                "finished": self.player.finished,
                "elapsed_s": self.player.elapsed_s,
                "duration_s": None if script is None else script["duration_s"],
                "cameras": [
                    {
                        "id": camera["id"],
                        "slot": camera["slot"],
                        "name": camera["name"],
                        "key": camera["key"],
                        "width": self.pack["width"],
                        "height": self.pack["height"],
                        "detections": self.live.get(camera["id"]).get("detections", []),
                    }
                    for camera in self.cameras
                ],
                "analysis": analysis,
                "position": position,
                "events": [
                    {"kind": row.kind, "detail": json.loads(row.detail_json), "occurred_at": row.occurred_at.isoformat()}
                    for row in rows
                ],
                "scene": self.scene(machine, analysis, position),
            }
        )
        if self.player.error is not None:
            body["error"] = str(self.player.error)
        return body

    def scene(self, machine, analysis, position) -> dict:
        room = self.pack["room"]
        fire = None
        if position is not None and position.get("status") == "ESTIMATED":
            values, vectors = np.linalg.eigh(np.array(position["covariance"], dtype=float))
            fire = {
                "xyz": position["xyz"],
                "radii": (np.sqrt(np.maximum(values, 0)) * 2).tolist(),
                "axes": vectors.tolist(),
            }
        spread = None if analysis is None else analysis.get("spread")
        return {
            "width_m": room["width_m"],
            "depth_m": room["depth_m"],
            "height_m": room["height_m"],
            "cameras": [
                {
                    "name": camera["name"],
                    "eye": camera["eye_m"],
                    "right": camera["right"],
                    "up": camera["up"],
                    "forward": camera["forward"],
                    "fov_y_deg": camera["fov_y_deg"],
                }
                for camera in self.cameras
            ],
            "fire": fire,
            "spread": spread,
            "gimbal": self._gimbal_pose(machine),
            "jet": self._jet(machine),
            "phase": None if machine is None else machine.phase,
            "alarm": self.suppression.alarm,
            "furniture": [_furniture("desk", item) for item in DESKS]
            + [_furniture("cabinet", CABINET), _furniture("board", BOARD)],
        }

    def frame(self, camera_id: int) -> bytes:
        with self.player._lock:
            jpeg = self.player.jpegs.get(camera_id)
        if jpeg is None:
            raise RuntimeError("这一路还没有画面")
        return jpeg

    def _seed(self) -> tuple[int, list[dict], dict]:
        pack = self.pack
        room_doc = pack["room"]
        now = datetime.now(UTC)
        session = self.session_factory()
        try:
            room = session.scalar(select(Room).where(Room.name == room_doc["name"]))
            if room is None:
                room = Room(name=room_doc["name"], scene_type=room_doc["scene_type"], created_at=now)
                session.add(room)
                session.flush()
            else:
                room.scene_type = room_doc["scene_type"]
            floor = self._floor(room_doc)
            self.evidence.put(floor["object_key"], floor.pop("bytes"), floor["content_type"])
            room.floor_plan_json = json.dumps(floor, ensure_ascii=False)
            cameras = []
            calibrations = {}
            for spec in pack["cameras"]:
                stream_key = f"demo-{spec['key']}"
                camera = session.scalar(select(Camera).where(Camera.stream_key == stream_key))
                document = json.dumps(
                    {
                        "intrinsics": spec["intrinsics"],
                        "distortion": spec["distortion"],
                        "landmarks": spec["landmarks"],
                        "image_size": [pack["width"], pack["height"]],
                    },
                    ensure_ascii=False,
                )
                if camera is None:
                    camera = Camera(
                        name=spec["name"],
                        source_type="FILE",
                        source_uri=str(pack["root"]),
                        stream_key=stream_key,
                        target_fps=pack["fps"],
                        calibration_json=document,
                        created_at=now,
                    )
                    session.add(camera)
                    session.flush()
                else:
                    camera.name = spec["name"]
                    camera.source_type = "FILE"
                    camera.calibration_json = document
                    camera.target_fps = pack["fps"]
                binding = session.scalar(
                    select(RoomCamera).where(RoomCamera.room_id == room.id, RoomCamera.slot == spec["slot"])
                )
                if binding is None:
                    session.add(RoomCamera(room_id=room.id, camera_id=camera.id, slot=spec["slot"]))
                else:
                    binding.camera_id = camera.id
                record = dict(spec)
                record["id"] = camera.id
                cameras.append(record)
                calibrations[camera.id] = json.loads(document)
            session.commit()
            return room.id, cameras, calibrations
        finally:
            session.close()

    def _floor(self, room: dict) -> dict:
        import cv2

        width, height = 480, 360
        image = np.full((height, width, 3), 232, dtype=np.uint8)
        scale = 50
        origin = (30, height - 30)

        def point(x: float, y: float) -> tuple[int, int]:
            return int(origin[0] + x * scale), int(origin[1] - y * scale)

        cv2.rectangle(image, point(0, room["depth_m"]), point(room["width_m"], 0), (90, 98, 108), 2)
        for region in room["combustibles"]:
            polygon = np.array([point(x, y) for x, y in region["polygon"]], dtype=np.int32)
            cv2.fillPoly(image, [polygon], (196, 176, 150))
            cv2.polylines(image, [polygon], True, (120, 96, 70), 1)
        ok, encoded = cv2.imencode(".png", image)
        if not ok:
            raise RuntimeError("平面图编码失败")
        return {
            "bytes": encoded.tobytes(),
            "object_key": "demo/floor.png",
            "content_type": "image/png",
            "origin_px": [origin[0], origin[1]],
            "meters_per_pixel": 1 / scale,
            "origin_world_m": [0, 0],
            "size_m": [room["width_m"], room["depth_m"]],
            "combustibles": room["combustibles"],
        }

    def _hardware(self):
        journal = Path(self.config.pump.journal_path)
        if self.config.demo.hardware == "serial":
            if not self.config.pump.enabled:
                raise RuntimeError("录像加真实串口时需要启用水泵")
            from ..pump.bridge import build_pump

            pump = build_pump(self.config)
            pump.config.zone_id = self.room_id
            pump.config.require_vlm = True
            pump.config.cooldown_seconds = 0
            pump.start()
            panel = None
            if self.config.panel.enabled:
                from fire_monitoring_inference.panel_v2 import PanelLink

                panel = PanelLink(self.config.panel.serial_port)
                panel.start()
            return pump, panel, True
        step = int(round(1000 / self.pack["fps"]))
        actuator = DeviceLink(ActuatorDevice(), step)
        panel_link = DeviceLink(PanelDevice(), step)
        pump = PumpController(
            config=PumpConfig(
                enabled=True,
                port="SIM",
                zone_id=self.room_id,
                duration_ms=5000,
                cooldown_seconds=0,
                min_confidence=self.config.pump.min_confidence,
                max_evidence_age_seconds=self.config.pump.max_evidence_age_seconds,
                require_vlm=True,
                local_min_confidence=self.config.pump.local_min_confidence,
                local_min_frames=self.config.pump.local_min_frames,
            ),
            journal_path=journal,
            transport=actuator,
        )
        return pump, _Panel(panel_link), False

    def _apply_gimbal(self) -> None:
        gimbal = self.pack["gimbal"]
        self.suppression.gimbal = GimbalParams.nominal(
            gimbal["p0"],
            yaw=math.radians(gimbal["yaw_deg"]),
            tilt_zero=gimbal["tilt_zero"],
        )
        self.suppression.speed = self.config.suppression.speed
        self.suppression.drag = self.config.suppression.drag

    def _clear_room(self) -> None:
        session = self.session_factory()
        try:
            alert_ids = list(session.scalars(select(Alert.id).where(Alert.room_id == self.room_id)))
            if alert_ids:
                session.execute(delete(AlertFrame).where(AlertFrame.alert_id.in_(alert_ids)))
                session.execute(delete(AlertClip).where(AlertClip.alert_id.in_(alert_ids)))
                session.execute(delete(Disposition).where(Disposition.alert_id.in_(alert_ids)))
                session.execute(delete(Alert).where(Alert.id.in_(alert_ids)))
            session.execute(delete(AlertEvent).where(AlertEvent.room_id == self.room_id))
            session.commit()
        finally:
            session.close()

    def _gimbal_pose(self, machine) -> dict:
        gimbal = self.suppression.gimbal
        actuator = self.suppression.snapshot(self.room_id)["actuator"]
        pan = actuator["pan"]
        tilt = actuator["tilt"]
        pan_rad = gimbal.pan_scale * (pan - gimbal.pan_zero)
        tilt_rad = gimbal.tilt_scale * (tilt - gimbal.tilt_zero)
        origin, direction = gimbal.pose(pan_rad, tilt_rad)
        return {
            "p0": gimbal.p0.tolist(),
            "origin": origin.tolist(),
            "direction": direction.tolist(),
            "pan_cdeg": pan,
            "tilt_cdeg": tilt,
            "laser": actuator["laser"] == "ON",
            "pump": actuator["pump"],
        }

    def _jet(self, machine) -> list[list[float]]:
        if machine is None or machine.angles is None:
            return []
        if machine.phase not in {"瞄准", "待喷", "喷射", "复核"}:
            return []
        gimbal = self.suppression.gimbal
        pan, tilt = machine.angles
        pan_rad = gimbal.pan_scale * (pan - gimbal.pan_zero)
        tilt_rad = gimbal.tilt_scale * (tilt - gimbal.tilt_zero)
        origin, _direction = gimbal.pose(pan_rad, tilt_rad)
        heading = gimbal.pose(pan_rad, 0.0)[1].copy()
        heading[2] = 0
        norm = float(np.linalg.norm(heading))
        if norm == 0:
            return []
        heading /= norm
        samples = integrate(tilt_rad, self.suppression.speed, self.suppression.drag, dt=0.04, t_max=2.2)
        target = None if machine.aim_point is None else np.asarray(machine.aim_point, dtype=float)
        points = []
        for row in samples[::3]:
            point = origin + heading * float(row[0]) + np.array([0.0, 0.0, float(row[1])])
            points.append([float(point[0]), float(point[1]), float(point[2])])
            if point[2] < 0.05:
                break
            if target is not None and len(points) > 4 and float(np.linalg.norm(point - target)) < 0.25:
                break
        return points


def _furniture(kind: str, bounds) -> dict:
    lo, hi = bounds
    return {"kind": kind, "min": [float(v) for v in lo], "max": [float(v) for v in hi]}
