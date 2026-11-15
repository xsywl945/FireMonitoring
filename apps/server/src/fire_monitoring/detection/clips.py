from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
from datetime import UTC, datetime, timedelta

from .capture import RING_FPS, CapturedFrame

logger = logging.getLogger("fire_monitoring.detection")

PRE_SECONDS = 5
POST_SECONDS = 10


def select_window(
    frames: list[CapturedFrame],
    alert_at: datetime,
    *,
    pre: float = PRE_SECONDS,
    post: float = POST_SECONDS,
) -> list[CapturedFrame]:
    start = alert_at - timedelta(seconds=pre)
    end = alert_at + timedelta(seconds=post)
    return [frame for frame in frames if start <= frame.captured_at <= end]


def encode_mp4(frames: list[CapturedFrame], fps: float) -> bytes:
    import cv2

    if not frames:
        raise RuntimeError("no frames for clip")
    if fps <= 0:
        raise RuntimeError("clip fps must be positive")
    first = frames[0].image
    height, width = first.shape[:2]
    fd, path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        os.remove(path)
        raise RuntimeError("mp4 writer failed")
    try:
        for frame in frames:
            image = frame.image
            if image.ndim == 2:
                image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
            if image.shape[0] != height or image.shape[1] != width:
                image = cv2.resize(image, (width, height))
            writer.write(image)
    finally:
        writer.release()
    data = open(path, "rb").read()
    os.remove(path)
    if not data:
        raise RuntimeError("mp4 is empty")
    return data


class ClipRecorder:
    def __init__(
        self,
        evidence,
        session_factory,
        events,
        on_fatal,
        *,
        pre: float = PRE_SECONDS,
        post: float = POST_SECONDS,
        fps: float = RING_FPS,
    ) -> None:
        self.evidence = evidence
        self.session_factory = session_factory
        self.events = events
        self.on_fatal = on_fatal
        self.pre = pre
        self.post = post
        self.fps = fps
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._threads: list[threading.Thread] = []

    def schedule(self, job, captures: dict) -> None:
        thread = threading.Thread(
            target=self._guard,
            args=(job, captures),
            name="alert-clip",
            daemon=True,
        )
        with self._lock:
            self._threads.append(thread)
        thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            threads = list(self._threads)
        for thread in threads:
            thread.join(timeout=5)
            if thread.is_alive():
                raise RuntimeError("clip thread did not stop")

    def _guard(self, job, captures: dict) -> None:
        try:
            self._save(job, captures)
        except Exception:
            if self._stop.is_set():
                return
            logger.exception("clip save failed")
            self.on_fatal()

    def _save(self, job, captures: dict) -> None:
        from ..models import AlertClip

        deadline = time.monotonic() + self.post + 30
        while job.alert_id is None:
            if self._stop.is_set():
                return
            if time.monotonic() > deadline:
                raise RuntimeError("alert was not recorded")
            self._stop.wait(0.02)
        remain = (job.started_at + timedelta(seconds=self.post) - datetime.now(UTC)).total_seconds()
        if remain > 0 and self._stop.wait(remain):
            return
        session = self.session_factory()
        try:
            for camera_id, capture in captures.items():
                frames = select_window(
                    capture.buffer.copy_ring(),
                    job.started_at,
                    pre=self.pre,
                    post=self.post,
                )
                if not frames:
                    continue
                data = encode_mp4(frames, self.fps)
                key = f"alerts/{job.alert_id}/clips/{camera_id}.mp4"
                self.evidence.put(key, data, "video/mp4")
                session.add(
                    AlertClip(
                        alert_id=job.alert_id,
                        camera_id=camera_id,
                        object_key=key,
                        started_at=frames[0].captured_at,
                        ended_at=frames[-1].captured_at,
                    )
                )
                self.events.publish(
                    {
                        "kind": "CLIP",
                        "alert_id": job.alert_id,
                        "room_id": job.room_id,
                        "camera_id": camera_id,
                        "occurred_at": datetime.now(UTC).isoformat(),
                    }
                )
            session.commit()
        finally:
            session.close()
