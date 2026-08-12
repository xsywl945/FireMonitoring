from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Protocol

from .contracts import Detection, EventType, utc_now
from .detectors.base import Detector
from .enrichment import IncidentEnrichmentJob, IncidentEnrichmentWorker
from .frames import FramePacket
from .live_frames import LiveFrameBuffer, draw_detections
from .pipeline import InferencePipeline


class CameraError(RuntimeError):
    """Raised when a local camera cannot be opened or read."""


class CameraSource(Protocol):
    def read(self) -> FramePacket:
        """Return the next captured frame."""

    def release(self) -> None:
        """Release the camera device."""


@dataclass(frozen=True, slots=True)
class LiveCameraConfig:
    site_id: int = 1
    zone_id: int = 1
    camera_id: int = 1
    target_fps: float = 5.0
    max_frames: int = 0
    preview: bool = False

    def __post_init__(self) -> None:
        if min(self.site_id, self.zone_id, self.camera_id) < 1:
            raise ValueError("site, zone, and camera identifiers must be positive")
        if self.target_fps < 0:
            raise ValueError("target_fps must be non-negative")
        if self.max_frames < 0:
            raise ValueError("max_frames must be non-negative")


@dataclass(frozen=True, slots=True)
class LiveRunSummary:
    frames_processed: int
    events_published: int
    incidents_confirmed: int
    stopped_by_user: bool

    def to_dict(self) -> dict[str, int | bool]:
        return {
            "framesProcessed": self.frames_processed,
            "eventsPublished": self.events_published,
            "incidentsConfirmed": self.incidents_confirmed,
            "stoppedByUser": self.stopped_by_user,
        }


class OpenCVCameraSource:
    """Small DirectShow-first adapter for one local Windows camera."""

    def __init__(
        self,
        *,
        camera_index: int,
        camera_id: int,
        width: int = 1280,
        height: int = 720,
        requested_fps: float = 5.0,
        cv2_module: Any | None = None,
    ) -> None:
        if camera_index < 0:
            raise ValueError("camera_index must be non-negative")
        if cv2_module is None:
            try:
                import cv2 as cv2_module
            except ImportError as exc:  # pragma: no cover - optional GPU stack
                raise RuntimeError(
                    "OpenCV is not installed. Run scripts/windows/setup-local-yolo.ps1 first."
                ) from exc

        self._cv2 = cv2_module
        self.camera_id = camera_id
        self.camera_index = camera_index
        self._capture = self._open(camera_index)
        if not self._capture.isOpened():
            self._capture.release()
            raise CameraError(
                f"cannot open camera index {camera_index}; close Camera/Teams/Zoom and retry"
            )

        self._set_if_available("CAP_PROP_FRAME_WIDTH", width)
        self._set_if_available("CAP_PROP_FRAME_HEIGHT", height)
        self._set_if_available("CAP_PROP_BUFFERSIZE", 1)
        if requested_fps > 0:
            self._set_if_available("CAP_PROP_FPS", requested_fps)

    def _open(self, camera_index: int) -> Any:
        if os.name == "nt" and hasattr(self._cv2, "CAP_DSHOW"):
            capture = self._cv2.VideoCapture(camera_index, self._cv2.CAP_DSHOW)
            if capture.isOpened():
                return capture
            capture.release()
        return self._cv2.VideoCapture(camera_index)

    def _set_if_available(self, property_name: str, value: float) -> None:
        property_id = getattr(self._cv2, property_name, None)
        if property_id is not None:
            self._capture.set(property_id, value)

    @property
    def backend_name(self) -> str:
        try:
            return str(self._capture.getBackendName())
        except Exception:
            return "unknown"

    @property
    def cv2_module(self) -> Any:
        return self._cv2

    def read(self) -> FramePacket:
        for _ in range(5):
            ok, image = self._capture.read()
            if ok and image is not None:
                height, width = image.shape[:2]
                return FramePacket(
                    camera_id=self.camera_id,
                    captured_at=utc_now(),
                    monotonic_ns=time.monotonic_ns(),
                    image=image,
                    width=int(width),
                    height=int(height),
                )
            time.sleep(0.05)
        raise CameraError(f"camera index {self.camera_index} stopped returning frames")

    def release(self) -> None:
        self._capture.release()


class LiveCameraRunner:
    """Run one camera through the existing detector, temporal, fusion, and event pipeline."""

    def __init__(
        self,
        *,
        source: CameraSource,
        detector: Detector,
        pipeline: InferencePipeline,
        config: LiveCameraConfig,
        cv2_module: Any | None = None,
        frame_buffer: LiveFrameBuffer | None = None,
        enrichment: IncidentEnrichmentWorker | None = None,
    ) -> None:
        self.source = source
        self.detector = detector
        self.pipeline = pipeline
        self.config = config
        self._cv2 = cv2_module
        self.frame_buffer = frame_buffer
        self.enrichment = enrichment

    def run(self) -> LiveRunSummary:
        processed = 0
        stopped_by_user = False
        period = 1 / self.config.target_fps if self.config.target_fps > 0 else 0
        next_due = 0.0
        last_status = time.monotonic()
        self.pipeline.runtime.start()
        try:
            while self.config.max_frames == 0 or processed < self.config.max_frames:
                packet = self.source.read()
                now = time.monotonic()
                if period and now < next_due:
                    continue

                inference_started = time.perf_counter()
                batches = self.detector.detect([packet.image])
                process_time_ms = (time.perf_counter() - inference_started) * 1000
                if len(batches) != 1:
                    raise RuntimeError("detector must return exactly one result for one frame")
                detections = batches[0]
                events = self.pipeline.process(
                    site_id=self.config.site_id,
                    zone_id=self.config.zone_id,
                    camera_id=self.config.camera_id,
                    view_role="SINGLE",
                    timestamp=packet.captured_at,
                    image_width=packet.width,
                    image_height=packet.height,
                    detections=detections,
                    process_time_ms=process_time_ms,
                )
                processed += 1
                next_due = now + period

                annotated = None
                if self.frame_buffer is not None:
                    annotated = self.frame_buffer.publish(
                        image=packet.image,
                        detections=detections,
                        captured_at=packet.captured_at,
                        process_time_ms=process_time_ms,
                        frames_processed=processed,
                    )

                confirmed_events = [
                    event for event in events if event.event_type == EventType.INCIDENT_CONFIRMED
                ]
                if self.enrichment is not None:
                    for confirmed_event in confirmed_events:
                        image = (
                            packet.image.copy() if hasattr(packet.image, "copy") else packet.image
                        )
                        self.enrichment.submit(
                            IncidentEnrichmentJob(
                                confirmed=confirmed_event,
                                frame=FramePacket(
                                    camera_id=packet.camera_id,
                                    captured_at=packet.captured_at,
                                    monotonic_ns=packet.monotonic_ns,
                                    image=image,
                                    width=packet.width,
                                    height=packet.height,
                                ),
                                detections=list(detections),
                            )
                        )

                if self.config.preview and self._show_preview(
                    annotated,
                    packet.image,
                    detections,
                    processed=processed,
                    process_time_ms=process_time_ms,
                ):
                    stopped_by_user = True
                    break

                if now - last_status >= 5:
                    confirmed = sum(
                        event.event_type == EventType.INCIDENT_CONFIRMED for event in events
                    )
                    print(
                        f"processed={processed} detections={len(detections)} "
                        f"inference={process_time_ms:.1f}ms confirmed={confirmed}",
                        file=sys.stderr,
                    )
                    last_status = now
        except KeyboardInterrupt:
            stopped_by_user = True
            self.pipeline.runtime.stop()
        except Exception:
            self.pipeline.runtime.fail("LIVE_CAMERA_FAILED")
            raise
        else:
            self.pipeline.runtime.stop()
        finally:
            self.source.release()
            if self.config.preview and self._cv2 is not None:
                self._cv2.destroyAllWindows()

        snapshot = self.pipeline.runtime.snapshot()
        return LiveRunSummary(
            frames_processed=int(snapshot["framesProcessed"]),
            events_published=int(snapshot["eventsPublished"]),
            incidents_confirmed=int(snapshot["incidentsConfirmed"]),
            stopped_by_user=stopped_by_user,
        )

    def _show_preview(
        self,
        annotated: Any | None,
        image: Any,
        detections: list[Detection],
        *,
        processed: int,
        process_time_ms: float,
    ) -> bool:
        if self._cv2 is None:
            raise RuntimeError("preview requires an OpenCV module")
        status = f"frames={processed} inference={process_time_ms:.1f}ms | Q/Esc: quit"
        rendered = (
            annotated
            if annotated is not None
            else draw_detections(self._cv2, image, detections, status=status)
        )
        self._cv2.imshow("Fire Monitoring - single camera research preview", rendered)
        return self._cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27)
