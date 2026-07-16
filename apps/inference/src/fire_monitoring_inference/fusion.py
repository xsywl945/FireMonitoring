from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .contracts import FusionObservation
from .temporal import TemporalEvidence, TemporalState


class FusionStatus(StrEnum):
    NONE = "NONE"
    CANDIDATE = "CANDIDATE"
    CONFIRMED = "CONFIRMED"


@dataclass(frozen=True, slots=True)
class FusionConfig:
    sync_window_ms: int = 500
    view_a_weight: float = 0.5
    view_b_weight: float = 0.5

    def __post_init__(self) -> None:
        if self.sync_window_ms < 0:
            raise ValueError("sync_window_ms cannot be negative")
        if self.view_a_weight < 0 or self.view_b_weight < 0:
            raise ValueError("camera weights cannot be negative")
        if self.view_a_weight + self.view_b_weight <= 0:
            raise ValueError("at least one camera weight must be positive")


@dataclass(frozen=True, slots=True)
class FusionDecision:
    status: FusionStatus
    score: float
    fusion_mode: str
    primary_type: str | None
    severity: str | None
    observations: tuple[FusionObservation, ...]
    started_at: datetime | None
    confirmed_at: datetime | None
    degraded: bool = False
    reason: str = ""


class DualCameraFusion:
    """Explainable decision-level fusion using camera arrival timestamps."""

    def __init__(self, config: FusionConfig | None = None) -> None:
        self.config = config or FusionConfig()

    def decide(
        self,
        evidence: list[TemporalEvidence],
        *,
        camera_health: dict[int, bool] | None = None,
        now: datetime | None = None,
    ) -> FusionDecision:
        health = camera_health or {}
        relevant = [
            item
            for item in evidence
            if item.state in {TemporalState.SUSPECT, TemporalState.CONFIRMED}
            and health.get(item.camera_id, True)
        ]
        if not relevant:
            return self._empty("no active evidence")

        # Keep one strongest class hypothesis per camera for the first decision-level MVP.
        strongest: dict[int, TemporalEvidence] = {}
        for item in relevant:
            previous = strongest.get(item.camera_id)
            rank = (item.state == TemporalState.CONFIRMED, item.score)
            if previous is None or rank > (
                previous.state == TemporalState.CONFIRMED,
                previous.score,
            ):
                strongest[item.camera_id] = item

        selected = sorted(strongest.values(), key=lambda item: item.last_seen_at, reverse=True)
        anchor_time = now or selected[0].last_seen_at
        selected = [
            item
            for item in selected
            if abs((anchor_time - item.last_seen_at).total_seconds() * 1000)
            <= self.config.sync_window_ms
        ]
        selected = selected[:2]
        if not selected:
            return self._empty("evidence outside synchronization window")

        if len(selected) == 2:
            delta_ms = abs(
                (selected[0].last_seen_at - selected[1].last_seen_at).total_seconds() * 1000
            )
            if delta_ms > self.config.sync_window_ms:
                selected = selected[:1]

        confirmed_count = sum(item.state == TemporalState.CONFIRMED for item in selected)
        if confirmed_count:
            status = FusionStatus.CONFIRMED
        else:
            status = FusionStatus.CANDIDATE

        weights = [self._weight(item) for item in selected]
        base_score = sum(
            item.score * weight for item, weight in zip(selected, weights, strict=False)
        ) / sum(weights)
        if len(selected) == 2 and confirmed_count == 2:
            score = min(1, base_score + 0.1)
        elif len(selected) == 2 and confirmed_count == 1:
            score = min(1, base_score + 0.03)
        elif confirmed_count == 1:
            score = base_score * 0.85
        else:
            score = base_score

        classes = {item.class_name for item in selected}
        primary_type = (
            "FIRE_AND_SMOKE" if len(classes) == 2 else "FIRE" if "fire" in classes else "SMOKE"
        )
        severity = self._severity(status, score, selected)
        observations = tuple(self._to_observation(item) for item in selected)
        started_at = min(item.first_seen_at for item in selected)
        confirmed_at = max(item.last_seen_at for item in selected) if confirmed_count else None
        configured_online = [online for online in health.values() if online]
        degraded = len(selected) == 1 and (len(health) > 1 and len(configured_online) < 2)
        reason = self._reason(selected, confirmed_count, degraded)
        return FusionDecision(
            status=status,
            score=score,
            fusion_mode="DUAL_CAMERA" if len(selected) == 2 else "SINGLE_CAMERA",
            primary_type=primary_type,
            severity=severity,
            observations=observations,
            started_at=started_at,
            confirmed_at=confirmed_at,
            degraded=degraded,
            reason=reason,
        )

    def _weight(self, item: TemporalEvidence) -> float:
        if item.view_role == "VIEW_A":
            return self.config.view_a_weight
        if item.view_role == "VIEW_B":
            return self.config.view_b_weight
        return 1

    @staticmethod
    def _severity(
        status: FusionStatus, score: float, evidence: list[TemporalEvidence]
    ) -> str | None:
        if status != FusionStatus.CONFIRMED:
            return None
        dual_confirmed = len(evidence) == 2 and all(
            item.state == TemporalState.CONFIRMED for item in evidence
        )
        if dual_confirmed:
            return "CRITICAL" if score >= 0.9 else "HIGH"
        if score >= 0.85:
            return "HIGH"
        if score >= 0.65:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _to_observation(item: TemporalEvidence) -> FusionObservation:
        return FusionObservation(
            cameraId=item.camera_id,
            viewRole=item.view_role,
            className=item.class_name,
            score=item.score,
            effectiveFrames=item.effective_frames,
            durationMs=item.duration_ms,
        )

    @staticmethod
    def _reason(selected: list[TemporalEvidence], confirmed_count: int, degraded: bool) -> str:
        if degraded:
            return "single-camera decision because another configured camera is offline"
        if len(selected) == 2 and confirmed_count == 2:
            return "two synchronized cameras confirmed the event"
        if len(selected) == 2 and confirmed_count == 1:
            return "one camera confirmed and the synchronized peer supplied supporting evidence"
        if confirmed_count == 1:
            return "single-camera confirmed evidence"
        return "candidate evidence has not met the confirmation threshold"

    @staticmethod
    def _empty(reason: str) -> FusionDecision:
        return FusionDecision(
            status=FusionStatus.NONE,
            score=0,
            fusion_mode="SINGLE_CAMERA",
            primary_type=None,
            severity=None,
            observations=(),
            started_at=None,
            confirmed_at=None,
            reason=reason,
        )
