from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass

from sqlalchemy import select

from ..alerts.pipeline import AlertPipeline, ConfirmedJob
from ..detection.capture import CameraCapture
from ..detection.ingest import DetectionHit, DetectionState, consume_frame
from ..models import Camera, Room, RoomCamera

logger = logging.getLogger("fire_monitoring.detection")


@dataclass
class Assignment:
    room_id: int
    camera_id: int
    stream_key: str
    target_fps: float
    calibration_json: str | None
    bound_camera_ids: list[int]


class LiveHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[int, dict] = {}

    def update(self, camera_id: int, payload: dict) -> None:
        with self._lock:
            self._items[camera_id] = payload

    def get(self, camera_id: int) -> dict:
        with self._lock:
            current = self._items.get(camera_id)
            if current is None:
                return {
                    "online": False,
                    "width": 0,
                    "height": 0,
                    "states": {"fire": "NORMAL", "smoke": "NORMAL"},
                    "detections": [],
                }
            return dict(current)


def due_cameras(assignments: list[Assignment], now: float, next_due: dict[int, float]) -> list[Assignment]:
    return [item for item in assignments if now >= next_due.get(item.camera_id, 0)]


class DetectionWorker:
    def __init__(
        self,
        config,
        session_factory,
        evidence,
        analyzer,
        sms,
        pump,
        live: LiveHub,
        events,
        *,
        detector=None,
        open_capture=None,
        localizer=None,
        on_fatal=None,
    ) -> None:
        self.config = config
        self.session_factory = session_factory
        self.live = live
        self.detector = detector
        self._open_capture = open_capture or self._open_rtsp
        self.on_fatal = on_fatal or _exit_process
        self.failed = False
        self.state = DetectionState()
        self.pipeline = AlertPipeline(
            config,
            session_factory,
            evidence,
            analyzer,
            sms,
            pump,
            events,
            localizer=localizer,
            on_fatal=self._fatal,
        )
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._assignments: list[Assignment] = []
        self._captures: dict[int, CameraCapture] = {}
        self._next_due: dict[int, float] = {}
        self._loaded_at = 0.0

    def start(self) -> None:
        if self.detector is None:
            from fire_monitoring_inference.detectors.ultralytics_adapter import UltralyticsDetector

            device = self.config.model.device
            resolved = int(device) if device.isdigit() else device
            self.detector = UltralyticsDetector(
                self.config.model.path,
                model_version=self.config.model.version,
                imgsz=self.config.model.imgsz,
                confidence=min(self.config.model.thresholds.fire, self.config.model.thresholds.smoke),
                device=resolved,
                half=resolved != "cpu",
            )
        self.pipeline.start()
        self._thread = threading.Thread(target=self._guard, name="detection", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                raise RuntimeError("detection thread did not stop")
        for capture in self._captures.values():
            capture.stop()
        self._captures.clear()
        self.pipeline.stop()

    @property
    def alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self.failed

    def _fatal(self) -> None:
        self.failed = True
        self.on_fatal()

    def _guard(self) -> None:
        try:
            self._loop()
        except Exception:
            logger.exception("detection thread failed")
            self._fatal()

    def _loop(self) -> None:
        while not self._stop.is_set():
            now = time.monotonic()
            if now - self._loaded_at >= 2:
                self._reload()
                self._loaded_at = now
            due = []
            for assignment in due_cameras(self._assignments, now, self._next_due):
                capture = self._captures.get(assignment.camera_id)
                frame = None if capture is None else capture.buffer.snapshot()
                if frame is None:
                    self._mark_offline(assignment.camera_id)
                    self._next_due[assignment.camera_id] = now + min(0.2, 1 / assignment.target_fps)
                    continue
                due.append((assignment, frame))
                self._next_due[assignment.camera_id] = now + 1 / assignment.target_fps
            if due:
                batches = self.detector.detect([frame.image for _assignment, frame in due])
                for (assignment, frame), detections in zip(due, batches, strict=True):
                    hits = [
                        DetectionHit(item.class_name, item.confidence, tuple(item.bbox_xyxy))
                        for item in detections
                    ]
                    snapshot = consume_frame(
                        room_id=assignment.room_id,
                        camera_id=assignment.camera_id,
                        bound_camera_ids=assignment.bound_camera_ids,
                        detections=hits,
                        jpeg=frame.jpeg,
                        width=frame.width,
                        height=frame.height,
                        timestamp=frame.captured_at,
                        state=self.state,
                        config=self.config,
                        on_alert=self._on_alert,
                    )
                    self.live.update(assignment.camera_id, snapshot)
            else:
                self._stop.wait(0.01)

    def _reload(self) -> None:
        session = self.session_factory()
        rooms = {room.id: room for room in session.scalars(select(Room))}
        cameras = {camera.id: camera for camera in session.scalars(select(Camera))}
        bindings = list(session.scalars(select(RoomCamera)))
        session.close()
        by_room: dict[int, list[RoomCamera]] = {}
        for binding in bindings:
            by_room.setdefault(binding.room_id, []).append(binding)
        assignments: list[Assignment] = []
        for room_id, room_bindings in by_room.items():
            if room_id not in rooms:
                continue
            ordered = sorted(room_bindings, key=lambda item: item.slot)
            bound_ids = [item.camera_id for item in ordered]
            for binding in ordered:
                camera = cameras.get(binding.camera_id)
                if camera is None:
                    continue
                assignments.append(
                    Assignment(
                        room_id=room_id,
                        camera_id=camera.id,
                        stream_key=camera.stream_key,
                        target_fps=camera.target_fps,
                        calibration_json=camera.calibration_json,
                        bound_camera_ids=bound_ids,
                    )
                )
        self._assignments = assignments
        wanted = {item.camera_id: item for item in assignments}
        for camera_id in list(self._captures):
            if camera_id not in wanted:
                self._captures.pop(camera_id).stop()
        for camera_id, assignment in wanted.items():
            if camera_id not in self._captures:
                capture = CameraCapture(assignment, self._open_capture, self._fatal)
                capture.start()
                self._captures[camera_id] = capture

    def _on_alert(self, draft) -> None:
        calibrations = {
            assignment.camera_id: json.loads(assignment.calibration_json)
            for assignment in self._assignments
            if assignment.room_id == draft.room_id and assignment.calibration_json
        }
        self.pipeline.submit(
            ConfirmedJob(
                room_id=draft.room_id,
                alert_type=draft.alert_type,
                started_at=draft.started_at,
                sources=draft.sources,
                calibrations=calibrations,
                frames=draft.frames,
                pump_observations=draft.pump_observations,
                confirmed_monotonic=time.perf_counter(),
            )
        )

    def _mark_offline(self, camera_id: int) -> None:
        current = self.live.get(camera_id)
        current["online"] = False
        self.live.update(camera_id, current)

    def _open_rtsp(self, assignment: Assignment):
        import cv2

        url = f"{self.config.mediamtx.rtsp_base}/{assignment.stream_key}"
        return cv2.VideoCapture(url, cv2.CAP_FFMPEG)


def _exit_process() -> None:
    import os

    os._exit(1)
