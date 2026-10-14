from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from .contracts import utc_now


class RuntimeState:
    def __init__(self, *, model_version: str) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {
            "status": "IDLE",
            "modelVersion": model_version,
            "startedAt": None,
            "updatedAt": utc_now(),
            "framesProcessed": 0,
            "eventsPublished": 0,
            "incidentsConfirmed": 0,
            "lastFrameAt": None,
            "lastError": None,
        }

    def set_camera(self, *, camera_id: int, zone_id: int) -> None:
        with self._lock:
            self._state.update(cameraId=camera_id, zoneId=zone_id)

    def prepare_camera(self, *, camera_id: int, zone_id: int, camera_index: int) -> None:
        with self._lock:
            self._state.update(
                status="STARTING", cameraId=camera_id, zoneId=zone_id, cameraIndex=camera_index,
                framesProcessed=0, eventsPublished=0, incidentsConfirmed=0,
                lastFrameAt=None, lastError=None,
            )

    def start(self) -> None:
        with self._lock:
            self._state.update(status="RUNNING", startedAt=utc_now(), lastError=None)
            self._state["updatedAt"] = utc_now()

    def stop(self) -> None:
        with self._lock:
            self._state["status"] = "STOPPED"
            self._state["updatedAt"] = utc_now()

    def fail(self, error_code: str) -> None:
        with self._lock:
            self._state["status"] = "FAILED"
            self._state["lastError"] = error_code
            self._state["updatedAt"] = utc_now()

    def record_frame(self, timestamp: datetime, published: int, confirmed: bool) -> None:
        with self._lock:
            self._state["framesProcessed"] += 1
            self._state["eventsPublished"] += published
            if confirmed:
                self._state["incidentsConfirmed"] += 1
            self._state["lastFrameAt"] = timestamp
            self._state["updatedAt"] = utc_now()

    def record_events(self, published: int, *, confirmed: bool = False) -> None:
        with self._lock:
            self._state["eventsPublished"] += published
            if confirmed:
                self._state["incidentsConfirmed"] += 1
            self._state["updatedAt"] = utc_now()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                key: value.isoformat().replace("+00:00", "Z")
                if isinstance(value, datetime)
                else value
                for key, value in self._state.items()
            }
