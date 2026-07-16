from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class TemporalState(StrEnum):
    NORMAL = "NORMAL"
    SUSPECT = "SUSPECT"
    CONFIRMED = "CONFIRMED"
    COOLDOWN = "COOLDOWN"


@dataclass(frozen=True, slots=True)
class TemporalConfig:
    n: int = 3
    m: int = 5
    candidate_n: int = 1
    min_confidence: float = 0.45
    clear_frames: int = 3
    cooldown_ms: int = 10_000

    def __post_init__(self) -> None:
        if not 1 <= self.candidate_n <= self.n <= self.m:
            raise ValueError("temporal thresholds must satisfy 1 <= candidate_n <= n <= m")
        if not 0 <= self.min_confidence <= 1:
            raise ValueError("min_confidence must be between zero and one")
        if self.clear_frames < 1 or self.cooldown_ms < 0:
            raise ValueError("clear_frames must be positive and cooldown_ms non-negative")


@dataclass(frozen=True, slots=True)
class _Sample:
    timestamp: datetime
    hit: bool
    confidence: float
    bbox_area: float


@dataclass(frozen=True, slots=True)
class TemporalEvidence:
    camera_id: int
    view_role: str
    class_name: str
    state: TemporalState
    score: float
    max_confidence: float
    average_confidence: float
    effective_frames: int
    duration_ms: int
    area_growth: float
    first_seen_at: datetime
    last_seen_at: datetime
    transitioned_from: TemporalState | None = None


class TemporalStateMachine:
    """Per-camera, per-class N/M evidence accumulator."""

    def __init__(
        self,
        *,
        camera_id: int,
        view_role: str,
        class_name: str,
        config: TemporalConfig | None = None,
    ) -> None:
        if class_name not in {"fire", "smoke"}:
            raise ValueError("class_name must be fire or smoke")
        if view_role not in {"VIEW_A", "VIEW_B", "SINGLE"}:
            raise ValueError("unsupported view role")
        self.camera_id = camera_id
        self.view_role = view_role
        self.class_name = class_name
        self.config = config or TemporalConfig()
        self.state = TemporalState.NORMAL
        self._samples: deque[_Sample] = deque(maxlen=self.config.m)
        self._miss_streak = 0
        self._first_seen_at: datetime | None = None
        self._last_seen_at: datetime | None = None
        self._cooldown_until: datetime | None = None

    def update(
        self,
        *,
        timestamp: datetime,
        confidence: float | None,
        bbox_area: float = 0,
    ) -> TemporalEvidence | None:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")

        transitioned_from: TemporalState | None = None
        if (
            self.state == TemporalState.COOLDOWN
            and self._cooldown_until is not None
            and timestamp >= self._cooldown_until
        ):
            transitioned_from = self.state
            self._reset(TemporalState.NORMAL)

        if self.state == TemporalState.COOLDOWN:
            return None

        value = float(confidence or 0)
        hit = confidence is not None and value >= self.config.min_confidence
        self._samples.append(_Sample(timestamp, hit, value if hit else 0, max(0, bbox_area)))

        old_state = self.state
        if hit:
            self._miss_streak = 0
            self._first_seen_at = self._first_seen_at or timestamp
            self._last_seen_at = timestamp
        else:
            self._miss_streak += 1

        hits = sum(sample.hit for sample in self._samples)
        if self.state == TemporalState.NORMAL and hits >= self.config.candidate_n:
            self.state = TemporalState.SUSPECT
        if self.state == TemporalState.SUSPECT and hits >= self.config.n:
            self.state = TemporalState.CONFIRMED

        if self._miss_streak >= self.config.clear_frames:
            if self.state == TemporalState.CONFIRMED:
                self.state = TemporalState.COOLDOWN
                self._cooldown_until = timestamp + timedelta(milliseconds=self.config.cooldown_ms)
            elif self.state == TemporalState.SUSPECT:
                self._reset(TemporalState.NORMAL)

        if old_state != self.state:
            transitioned_from = old_state

        if self.state in {TemporalState.NORMAL, TemporalState.COOLDOWN}:
            return None
        hit_samples = [sample for sample in self._samples if sample.hit]
        if not hit_samples or self._first_seen_at is None or self._last_seen_at is None:
            return None
        confidences = [sample.confidence for sample in hit_samples]
        areas = [sample.bbox_area for sample in hit_samples]
        average = sum(confidences) / len(confidences)
        persistence = min(1, len(hit_samples) / self.config.n)
        score = min(1, average * 0.8 + persistence * 0.2)
        first_area = areas[0]
        area_growth = 0 if first_area <= 0 else (areas[-1] - first_area) / first_area
        duration_ms = max(
            0,
            int((self._last_seen_at - self._first_seen_at).total_seconds() * 1000),
        )
        return TemporalEvidence(
            camera_id=self.camera_id,
            view_role=self.view_role,
            class_name=self.class_name,
            state=self.state,
            score=score,
            max_confidence=max(confidences),
            average_confidence=average,
            effective_frames=len(hit_samples),
            duration_ms=duration_ms,
            area_growth=area_growth,
            first_seen_at=self._first_seen_at,
            last_seen_at=self._last_seen_at,
            transitioned_from=transitioned_from,
        )

    def _reset(self, state: TemporalState) -> None:
        self.state = state
        self._samples.clear()
        self._miss_streak = 0
        self._first_seen_at = None
        self._last_seen_at = None
        self._cooldown_until = None
