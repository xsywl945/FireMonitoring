from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from ..alerts.service import confirm_alert
from ..detection.ingest import DetectionHit, DetectionState, consume_frame
from ..localization.observe import build_pose, geometry_locate
from ..models import Camera, Room, RoomCamera


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


class DetectionWorker:
    def __init__(self, config, session_factory, evidence, analyzer, sms, pump, live: LiveHub) -> None:
        self.config = config
        self.session_factory = session_factory
        self.evidence = evidence
        self.analyzer = analyzer
        self.sms = sms
        self.pump = pump
        self.live = live
        self.state = DetectionState()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._caps: dict[int, object] = {}
        self._poses: dict[int, object] = {}
        self._pose_key: dict[int, str] = {}
        self._assignments: list[Assignment] = []
        self._loaded_at = 0.0
        self.detector = None

    def start(self) -> None:
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
        self._thread = threading.Thread(target=self._loop, name="detection", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        for cap in self._caps.values():
            cap.release()
        self._caps.clear()

    def _loop(self) -> None:
        import time

        while not self._stop.is_set():
            now = time.monotonic()
            if now - self._loaded_at >= 2:
                self._reload()
                self._loaded_at = now
            for assignment in self._assignments:
                self._process(assignment)
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
                self._refresh_pose(camera.id, camera.calibration_json)
        self._assignments = assignments

    def _refresh_pose(self, camera_id: int, raw: str | None) -> None:
        if not raw:
            self._poses.pop(camera_id, None)
            self._pose_key.pop(camera_id, None)
            return
        if self._pose_key.get(camera_id) == raw:
            return
        self._poses[camera_id] = build_pose(
            json.loads(raw), self.config.localization.landmark_sigma_px
        )
        self._pose_key[camera_id] = raw

    def _process(self, assignment: Assignment) -> None:
        import cv2

        url = f"{self.config.mediamtx.rtsp_base}/{assignment.stream_key}"
        cap = self._caps.get(assignment.camera_id)
        if cap is None or not cap.isOpened():
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            self._caps[assignment.camera_id] = cap
        ok, frame = cap.read()
        if not ok:
            cap.release()
            self._caps.pop(assignment.camera_id, None)
            current = self.live.get(assignment.camera_id)
            current["online"] = False
            self.live.update(assignment.camera_id, current)
            return
        height, width = frame.shape[:2]
        detections = self.detector.detect([frame])[0]
        hits = [
            DetectionHit(item.class_name, item.confidence, tuple(item.bbox_xyxy))
            for item in detections
        ]
        encoded, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        jpeg = buffer.tobytes() if encoded else b""
        timestamp = datetime.now(UTC)
        snapshot = consume_frame(
            room_id=assignment.room_id,
            camera_id=assignment.camera_id,
            bound_camera_ids=assignment.bound_camera_ids,
            detections=hits,
            jpeg=jpeg,
            width=width,
            height=height,
            timestamp=timestamp,
            state=self.state,
            config=self.config,
            on_alert=self._on_alert,
        )
        self.live.update(assignment.camera_id, snapshot)

    def _on_alert(self, draft) -> None:
        poses = {
            item.camera_id: self._poses[item.camera_id]
            for item in draft.sources
            if item.camera_id in self._poses
        }
        session = self.session_factory()
        try:
            confirm_alert(
                session,
                room_id=draft.room_id,
                alert_type=draft.alert_type,
                started_at=draft.started_at,
                sources=draft.sources,
                poses=poses,
                frames=draft.frames,
                pump_observations=draft.pump_observations,
                config=self.config,
                evidence=self.evidence,
                analyzer=self.analyzer,
                sms=self.sms,
                pump=self.pump,
                locate_fn=geometry_locate,
            )
        finally:
            session.close()
