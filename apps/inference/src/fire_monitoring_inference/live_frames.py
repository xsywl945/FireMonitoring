from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import datetime
from typing import Any

from .contracts import Detection


def draw_detections(
    cv2_module: Any,
    image: Any,
    detections: list[Detection],
    *,
    status: str,
) -> Any:
    output = image.copy()
    for detection in detections:
        x1, y1, x2, y2 = (int(value) for value in detection.bbox_xyxy)
        color = (0, 0, 255) if detection.class_name == "fire" else (0, 165, 255)
        cv2_module.rectangle(output, (x1, y1), (x2, y2), color, 2)
        label = f"{detection.class_name} {detection.confidence:.2f}"
        cv2_module.putText(
            output,
            label,
            (max(0, x1), max(20, y1 - 8)),
            cv2_module.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            2,
            cv2_module.LINE_AA,
        )
    cv2_module.putText(
        output,
        status,
        (12, 28),
        cv2_module.FONT_HERSHEY_SIMPLEX,
        0.65,
        (0, 255, 0),
        2,
        cv2_module.LINE_AA,
    )
    return output


def encode_jpeg(cv2_module: Any, image: Any, *, quality: int = 85) -> bytes:
    ok, encoded = cv2_module.imencode(
        ".jpg", image, [int(cv2_module.IMWRITE_JPEG_QUALITY), quality]
    )
    if not ok:
        raise RuntimeError("OpenCV could not encode the evidence JPEG")
    return bytes(encoded)


class LiveFrameBuffer:
    """Latest annotated JPEG and metadata for the local browser monitor."""

    def __init__(self, cv2_module: Any) -> None:
        self._cv2 = cv2_module
        self._condition = threading.Condition()
        self._sequence = 0
        self._jpeg: bytes | None = None
        self._metadata: dict[str, Any] = {"ready": False, "detections": []}

    def publish(
        self,
        *,
        image: Any,
        detections: list[Detection],
        captured_at: datetime,
        process_time_ms: float,
        frames_processed: int,
    ) -> Any:
        status = f"frames={frames_processed} inference={process_time_ms:.1f}ms"
        annotated = draw_detections(self._cv2, image, detections, status=status)
        jpeg = encode_jpeg(self._cv2, annotated)
        height, width = annotated.shape[:2]
        with self._condition:
            self._sequence += 1
            self._jpeg = jpeg
            self._metadata = {
                "ready": True,
                "capturedAt": captured_at.isoformat().replace("+00:00", "Z"),
                "imageWidth": int(width),
                "imageHeight": int(height),
                "processTimeMs": process_time_ms,
                "framesProcessed": frames_processed,
                "detections": [item.model_dump(by_alias=True, mode="json") for item in detections],
            }
            self._condition.notify_all()
        return annotated

    def clear(self) -> None:
        with self._condition:
            self._jpeg = None
            self._metadata = {"ready": False, "detections": []}
            self._condition.notify_all()

    def status(self) -> dict[str, Any]:
        with self._condition:
            return dict(self._metadata)

    def jpeg_after(self, sequence: int, timeout: float = 5.0) -> tuple[int, bytes | None]:
        with self._condition:
            self._condition.wait_for(
                lambda: self._sequence > sequence and self._jpeg is not None,
                timeout=timeout,
            )
            return self._sequence, self._jpeg

    def mjpeg(self) -> Iterator[bytes]:
        sequence = -1
        while True:
            sequence, jpeg = self.jpeg_after(sequence)
            if jpeg is None:
                continue
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
