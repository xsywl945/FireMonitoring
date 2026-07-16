from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..contracts import Detection


class MockDetector:
    """Dependency-free detector for deterministic replay and integration tests."""

    model_version = "mock-fire-yolo-0.1.0"

    def detect(self, images: list[Any]) -> list[list[Detection]]:
        batches: list[list[Detection]] = []
        for image in images:
            raw: Any = []
            if isinstance(image, Mapping):
                raw = image.get("detections", [])
            elif hasattr(image, "detections"):
                raw = image.detections
            batches.append(
                [
                    item if isinstance(item, Detection) else Detection.model_validate(item)
                    for item in raw
                ]
            )
        return batches
