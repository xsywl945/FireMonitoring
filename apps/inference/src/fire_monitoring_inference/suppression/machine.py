from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .aim import solve_aim
from .feedback import corrected_aim, ellipse_sweep, plan_spray
from .interlock import aim_probability, resolved_rules, spray_block
from .voice import (
    ESTOP_VOICE,
    EXTINGUISHED_VOICE,
    PENDING_VOICE,
    PERSON_VOICE,
    fire_voice,
    prohibited_voice,
    smoke_voice,
)

PANEL = {
    "监视": "GREEN",
    "疑似": "YELLOW",
    "已确认": "RED_BLINK",
    "瞄准": "RED_BLINK",
    "待喷": "RED_SOLID",
    "喷射": "RED_SOLID",
    "复核": "RED_BLINK",
    "已扑灭": "YELLOW",
    "需人工处置": "RED_BLINK",
    "锁定": "ALT",
}
KIND = {
    "监视": "SUP_MONITOR",
    "疑似": "SUP_SUSPECTED",
    "已确认": "SUP_CONFIRMED",
    "瞄准": "SUP_AIM",
    "待喷": "SUP_PENDING",
    "喷射": "SUP_SPRAY",
    "复核": "SUP_REVIEW",
    "已扑灭": "SUP_OUT",
    "需人工处置": "SUP_MANUAL",
    "锁定": "SUP_LOCKED",
}
BLOCK_KIND = "SUP_BLOCK"


@dataclass
class Effect:
    kind: str
    phase: str
    panel: str | None = None
    voice: str | None = None
    laser: bool | None = None
    aim: tuple[int, int] | None = None
    run: bool = False
    stop: bool = False
    latch: bool = False
    detail: dict = field(default_factory=dict)


@dataclass
class MachineConfig:
    pending_s: float = 3.0
    spray_s: float = 5.0
    review_s: float = 5.0
    clear_s: float = 3.0
    max_corrections: int = 2
    max_water_s: float = 15.0
    area_drop: float = 0.2


@dataclass
class Shot:
    now: float
    room_name: str
    scene: str
    local_fire: bool
    smoke: bool
    analysis: dict | None
    position: dict | None
    heartbeat_ok: bool
    persons: list
    flame_present: bool
    flame_area: float | None
    landing: np.ndarray | None
    web_estop: bool
    firmware_latch: str
    admin_unlock: bool
    room_size: tuple[float, float]
    gimbal: object
    speed: float
    drag: float
    grade: str
    pump_enabled: bool
    zone_ok: bool
    evidence_age_s: float
    max_evidence_age_s: float
    cancelled: bool
    require_vlm: bool
    cooldown_elapsed: bool
    max_std_m: float
    cover_radius_m: float
    cover_threshold: float
    person_distance_m: float
    max_water_s: float = 15.0
    manual_aim: tuple[int, int] | None = None
    manual_spray: bool = False


class RoomMachine:
    def __init__(self, config: MachineConfig | None = None) -> None:
        self.config = config or MachineConfig()
        self.phase = "监视"
        self.block: str | None = None
        self.corrections = 0
        self.pending_at: float | None = None
        self.spray_at: float | None = None
        self.review_at: float | None = None
        self.clear_since: float | None = None
        self.baseline_area: float | None = None
        self.aim_point: np.ndarray | None = None
        self.sweep: list[np.ndarray] | None = None
        self.sweep_i = 0
        self.cover_probability: float | None = None
        self.angles: tuple[int, int] | None = None

    def step(self, shot: Shot) -> list[Effect]:
        out: list[Effect] = []
        locked = shot.web_estop or shot.firmware_latch in {"LATCHED", "ARMED"}
        if self.phase == "锁定" or locked:
            if self.phase != "锁定":
                self._mark(
                    out,
                    "锁定",
                    panel="ALT",
                    voice=ESTOP_VOICE,
                    laser=False,
                    stop=True,
                    latch=True,
                    detail={"reason": "ESTOP"},
                )
                return out
            self._unlock(shot, out)
            return out
        if shot.manual_aim is not None:
            out.append(
                Effect(
                    kind="SUP_AIM",
                    phase=self.phase,
                    aim=shot.manual_aim,
                    laser=True,
                    detail={"manual": True},
                )
            )
        self._progress(shot, out)
        return out

    def _unlock(self, shot, out: list[Effect]) -> None:
        if shot.web_estop or shot.firmware_latch == "LATCHED" or not shot.admin_unlock:
            if shot.admin_unlock and shot.firmware_latch == "LATCHED":
                out.append(
                    Effect(
                        kind=BLOCK_KIND,
                        phase="锁定",
                        detail={"reason": "ERR_RESET"},
                    )
                )
            return
        self.corrections = 0
        self.sweep = None
        self.block = None
        self._mark(out, "监视", panel="GREEN", detail={"unlock": True})

    def _progress(self, shot, out: list[Effect]) -> None:
        for _ in range(8):
            before = (self.phase, self.block)
            if self.phase == "监视":
                self._from_monitor(shot, out)
            elif self.phase == "疑似":
                self._from_suspected(shot, out)
            elif self.phase in {"已确认", "瞄准"}:
                self._arm(shot, out)
            elif self.phase == "待喷":
                if shot.now - self.pending_at >= self.config.pending_s:
                    self._spray(shot, out)
            elif self.phase == "喷射":
                if shot.now - self.spray_at >= self.config.spray_s:
                    self.review_at = shot.now
                    self.clear_since = None
                    self._mark(out, "复核", panel="RED_BLINK")
            elif self.phase == "复核":
                self._review(shot, out)
            if (self.phase, self.block) == before:
                return

    def _from_monitor(self, shot, out: list[Effect]) -> None:
        if shot.local_fire or shot.manual_spray:
            self._mark(out, "已确认", panel="RED_BLINK")
            return
        if shot.smoke:
            self._mark(out, "疑似", panel="YELLOW", voice=smoke_voice(shot.room_name))

    def _from_suspected(self, shot, out: list[Effect]) -> None:
        if shot.local_fire or shot.manual_spray:
            self._mark(out, "已确认", panel="RED_BLINK")
            return
        if not shot.smoke:
            self._mark(out, "监视", panel="GREEN")

    def _arm(self, shot, out: list[Effect]) -> None:
        if not shot.local_fire and not shot.manual_spray:
            self._mark(out, "监视", panel="GREEN")
            return
        rules = resolved_rules(shot.scene, shot.analysis)
        if rules["water_prohibited"]:
            self._mark(
                out,
                "已确认",
                reason="WATER_PROHIBITED",
                panel="RED_BLINK",
                voice=prohibited_voice(rules),
                detail={"reason": "WATER_PROHIBITED", "classes": rules["classes"]},
            )
            return
        target = self._target(shot)
        aim = None if target is None else solve_aim(shot.gimbal, target, shot.speed, shot.drag)
        probability = aim_probability(shot, aim)
        self.cover_probability = probability
        sweeping = self.sweep is not None
        reason = spray_block(shot, aim, probability, sweeping=sweeping)
        if reason == "COVERAGE" and self.sweep is None and shot.position and shot.position.get("xyz"):
            budget = max(1, int(shot.max_water_s // self.config.spray_s))
            plan = plan_spray(
                shot.position["xyz"],
                shot.position["covariance"],
                shot.cover_radius_m,
                max_points=budget,
                threshold=shot.cover_threshold,
            )
            self.cover_probability = plan["nominal"]
            probability = plan["nominal"]
            if plan["spray"]:
                self.sweep = plan["points"]
                self.sweep_i = 0
                target = self.sweep[0]
                aim = solve_aim(shot.gimbal, target, shot.speed, shot.drag)
                reason = spray_block(shot, aim, probability, sweeping=True)
        if reason == "PERSON":
            self._mark(
                out,
                "已确认",
                reason=reason,
                panel="RED_BLINK",
                voice=PERSON_VOICE,
                detail=self._detail(shot, reason, probability),
            )
            return
        if reason is not None:
            self._mark(
                out,
                "已确认",
                reason=reason,
                panel="RED_BLINK",
                detail=self._detail(shot, reason, probability),
            )
            return
        self.aim_point = np.asarray(target, dtype=float)
        self.angles = (aim.pan_cdeg, aim.tilt_cdeg)
        if self.phase != "瞄准":
            voice = fire_voice(shot.room_name, self.aim_point, shot.room_size, shot.grade)
            self._mark(
                out,
                "瞄准",
                panel="RED_BLINK",
                voice=voice,
                laser=True,
                aim=self.angles,
                detail=self._detail(shot, None, probability),
            )
        self.pending_at = shot.now
        self._mark(
            out,
            "待喷",
            panel="RED_SOLID",
            voice=PENDING_VOICE,
            laser=True,
            aim=self.angles,
            detail=self._detail(shot, None, probability),
        )

    def _spray(self, shot, out: list[Effect]) -> None:
        self.spray_at = shot.now
        self.baseline_area = shot.flame_area
        self._mark(
            out,
            "喷射",
            panel="RED_SOLID",
            run=True,
            laser=True,
            aim=self.angles,
            detail=self._detail(shot, None, self.cover_probability),
        )

    def _review(self, shot, out: list[Effect]) -> None:
        if not shot.flame_present:
            if self.clear_since is None:
                self.clear_since = shot.now
            if shot.now - self.clear_since >= self.config.clear_s:
                self.sweep = None
                self._mark(
                    out,
                    "已扑灭",
                    panel="YELLOW",
                    voice=EXTINGUISHED_VOICE,
                    laser=False,
                )
            return
        self.clear_since = None
        if shot.now - self.review_at < self.config.review_s:
            return
        dropped = (
            shot.flame_area is not None
            and self.baseline_area not in (None, 0)
            and shot.flame_area <= self.baseline_area * (1 - self.config.area_drop)
        )
        if dropped:
            return
        if self.corrections >= self.config.max_corrections:
            self._mark(out, "需人工处置", panel="RED_BLINK", stop=True, detail={"reason": "MANUAL"})
            return
        self.corrections += 1
        if shot.landing is not None and self.aim_point is not None:
            self.aim_point = corrected_aim(self.aim_point, shot.landing)
            self.sweep = None
            detail = {"correction": self.corrections, "mode": "landing"}
        else:
            mean = self.aim_point if self.aim_point is not None else np.array(shot.position["xyz"])
            cov = shot.position["covariance"] if shot.position and shot.position.get("covariance") else np.eye(3)
            budget = max(1, int(shot.max_water_s // self.config.spray_s))
            points = ellipse_sweep(mean, cov, shot.cover_radius_m, max_points=budget)
            self.sweep = points or [np.asarray(mean, dtype=float)]
            self.sweep_i = min(self.corrections, len(self.sweep) - 1)
            self.aim_point = self.sweep[self.sweep_i]
            detail = {"correction": self.corrections, "mode": "sweep"}
        self._mark(out, "瞄准", panel="RED_BLINK", laser=True, detail=detail)

    def _target(self, shot):
        if self.sweep is not None:
            return self.sweep[min(self.sweep_i, len(self.sweep) - 1)]
        if self.aim_point is not None and self.corrections:
            return self.aim_point
        return _xyz(shot)

    def _detail(self, shot, reason, probability) -> dict:
        return {
            "reason": reason,
            "cover_probability": probability,
            "cover_threshold": shot.cover_threshold,
            "message": "超出喷射范围" if reason == "OUT_OF_RANGE" else None,
        }

    def _mark(
        self,
        out: list[Effect],
        phase: str,
        *,
        reason: str | None = None,
        panel: str | None = None,
        voice: str | None = None,
        laser: bool | None = None,
        aim: tuple[int, int] | None = None,
        run: bool = False,
        stop: bool = False,
        latch: bool = False,
        detail: dict | None = None,
    ) -> None:
        if phase == self.phase and reason == self.block and not run:
            return
        self.phase = phase
        self.block = reason
        payload = dict(detail or {})
        if reason is not None:
            payload["reason"] = reason
        out.append(
            Effect(
                kind=KIND[phase] if reason is None else BLOCK_KIND if phase == "已确认" else KIND[phase],
                phase=phase,
                panel=panel or PANEL[phase],
                voice=voice,
                laser=laser,
                aim=aim,
                run=run,
                stop=stop,
                latch=latch,
                detail=payload,
            )
        )


def _xyz(shot):
    if shot.position is None or shot.position.get("status") != "ESTIMATED":
        return None
    return shot.position["xyz"]
