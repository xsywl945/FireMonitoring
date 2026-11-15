from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class HealthView:
    online: bool
    frozen: bool
    blur: bool
    blur_variance: float | None


@dataclass(frozen=True)
class Fault:
    camera_id: int
    kind: str


def blur_variance(frame: np.ndarray) -> float:
    import cv2

    gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


class HealthTracker:
    def __init__(self, freeze_seconds: float, blur_variance_limit: float, offline_seconds: float) -> None:
        self.freeze_seconds = freeze_seconds
        self.blur_variance_limit = blur_variance_limit
        self.offline_seconds = offline_seconds
        self._prev: dict[int, np.ndarray] = {}
        self._prev_at: dict[int, float] = {}
        self._freeze_since: dict[int, float] = {}
        self._offline_since: dict[int, float] = {}
        self._active: dict[int, set[str]] = {}

    def observe(
        self, camera_id: int, frame: np.ndarray | None, now: float
    ) -> tuple[HealthView, list[Fault]]:
        if frame is None:
            return self._offline(camera_id, now)
        self._offline_since.pop(camera_id, None)
        previous = self._prev.get(camera_id)
        same = (
            previous is not None
            and previous.shape == frame.shape
            and np.array_equal(previous, frame)
        )
        if same:
            self._freeze_since.setdefault(camera_id, self._prev_at[camera_id])
            frozen = now - self._freeze_since[camera_id] >= self.freeze_seconds
        else:
            self._freeze_since.pop(camera_id, None)
            frozen = False
        variance = blur_variance(frame)
        blur = variance < self.blur_variance_limit
        self._prev[camera_id] = frame.copy()
        self._prev_at[camera_id] = now
        faults = [
            fault
            for fault in (
                self._edge(camera_id, "OFFLINE", False),
                self._edge(camera_id, "FROZEN", frozen),
                self._edge(camera_id, "BLUR", blur),
            )
            if fault is not None
        ]
        return HealthView(True, frozen, blur, variance), faults

    def _offline(self, camera_id: int, now: float) -> tuple[HealthView, list[Fault]]:
        self._offline_since.setdefault(camera_id, now)
        self._prev.pop(camera_id, None)
        self._prev_at.pop(camera_id, None)
        self._freeze_since.pop(camera_id, None)
        offline = now - self._offline_since[camera_id] >= self.offline_seconds
        self._edge(camera_id, "FROZEN", False)
        self._edge(camera_id, "BLUR", False)
        fault = self._edge(camera_id, "OFFLINE", offline)
        faults = [] if fault is None else [fault]
        return HealthView(False, False, False, None), faults

    def _edge(self, camera_id: int, kind: str, active: bool) -> Fault | None:
        flags = self._active.setdefault(camera_id, set())
        if active and kind not in flags:
            flags.add(kind)
            return Fault(camera_id, kind)
        if not active and kind in flags:
            flags.discard(kind)
        return None
