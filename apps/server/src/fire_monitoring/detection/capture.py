from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime

RING_FPS = 2
RING_SECONDS = 15
logger = logging.getLogger("fire_monitoring.detection")


@dataclass(frozen=True)
class CapturedFrame:
    image: object
    jpeg: bytes
    captured_at: datetime
    width: int
    height: int


class FrameBuffer:
    def __init__(self, ring_fps: float = RING_FPS, ring_seconds: float = RING_SECONDS) -> None:
        self.ring_fps = ring_fps
        self.ring: deque[CapturedFrame] = deque(maxlen=max(1, int(ring_fps * ring_seconds)))
        self.latest: CapturedFrame | None = None
        self._last_ring: float | None = None
        self._lock = threading.Lock()

    def push(self, frame: CapturedFrame, now: float) -> None:
        with self._lock:
            self.latest = frame
            if self._last_ring is None or now - self._last_ring >= 1 / self.ring_fps:
                self.ring.append(frame)
                self._last_ring = now

    def snapshot(self) -> CapturedFrame | None:
        with self._lock:
            return self.latest

    def clear(self) -> None:
        with self._lock:
            self.latest = None


class CameraCapture:
    def __init__(self, assignment, open_capture, on_fatal) -> None:
        self.assignment = assignment
        self._open_capture = open_capture
        self._on_fatal = on_fatal
        self.buffer = FrameBuffer()
        self._capture = None
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._guard,
            name=f"capture-{assignment.camera_id}",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        capture = self._capture
        if capture is not None:
            capture.release()
        self._thread.join(timeout=5)
        if self._thread.is_alive():
            raise RuntimeError(f"capture {self.assignment.camera_id} did not stop")

    def _guard(self) -> None:
        try:
            self._run()
        except Exception:
            logger.exception("capture %s failed", self.assignment.camera_id)
            self._on_fatal()

    def _run(self) -> None:
        self._capture = self._open_capture(self.assignment)
        while not self._stop.is_set():
            ok, frame = self._capture.read()
            if not ok or frame is None:
                self._capture.release()
                self.buffer.clear()
                if self._stop.wait(0.2):
                    return
                self._capture = self._open_capture(self.assignment)
                continue
            self.buffer.push(_encode(frame.copy()), _now())
        self._capture.release()


def _now() -> float:
    import time

    return time.monotonic()


def _encode(frame) -> CapturedFrame:
    import cv2
    from datetime import UTC, datetime

    height, width = frame.shape[:2]
    ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    if not ok:
        raise RuntimeError("jpeg encode failed")
    return CapturedFrame(
        image=frame,
        jpeg=encoded.tobytes(),
        captured_at=datetime.now(UTC),
        width=width,
        height=height,
    )
