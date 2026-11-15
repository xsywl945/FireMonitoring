from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Fault:
    camera_id: int
    kind: str


class FaultTracker:
    def __init__(self, freeze_seconds: float, offline_seconds: float) -> None:
        self.freeze_seconds = freeze_seconds
        self.offline_seconds = offline_seconds
        self._since: dict[tuple[int, str], float] = {}
        self._active: dict[int, str | None] = {}

    def update(self, camera_id: int, status: str, now: float) -> list[Fault]:
        kind = {"frozen": "FROZEN", "blur": "BLUR", "offline": "OFFLINE"}.get(status)
        if kind is None:
            self._active[camera_id] = None
            self._since.pop((camera_id, "FROZEN"), None)
            self._since.pop((camera_id, "OFFLINE"), None)
            return []
        if kind == "FROZEN":
            self._since.setdefault((camera_id, "FROZEN"), now)
            ready = now - self._since[(camera_id, "FROZEN")] >= self.freeze_seconds
        elif kind == "OFFLINE":
            self._since.setdefault((camera_id, "OFFLINE"), now)
            ready = now - self._since[(camera_id, "OFFLINE")] >= self.offline_seconds
        else:
            ready = True
        if kind != "FROZEN":
            self._since.pop((camera_id, "FROZEN"), None)
        if kind != "OFFLINE":
            self._since.pop((camera_id, "OFFLINE"), None)
        if not ready or self._active.get(camera_id) == kind:
            return []
        self._active[camera_id] = kind
        return [Fault(camera_id, kind)]
