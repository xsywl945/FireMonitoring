from __future__ import annotations

import json
import time
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from .contracts import Detection, EventEnvelope, StrictModel
from .detectors.base import Detector
from .pipeline import InferencePipeline


class ReplayFrame(StrictModel):
    site_id: int = Field(default=1, alias="siteId", ge=1)
    zone_id: int = Field(default=1, alias="zoneId", ge=1)
    camera_id: int = Field(alias="cameraId", ge=1)
    view_role: Literal["VIEW_A", "VIEW_B", "SINGLE"] = Field(alias="viewRole")
    timestamp: datetime
    image_width: int = Field(default=1280, alias="imageWidth", ge=1)
    image_height: int = Field(default=720, alias="imageHeight", ge=1)
    process_time_ms: float = Field(default=12, alias="processTimeMs", ge=0)
    detections: list[Detection] = Field(default_factory=list, max_length=100)

    @field_validator("timestamp")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return value


def load_jsonl(path: Path) -> list[ReplayFrame]:
    frames: list[ReplayFrame] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            try:
                frames.append(ReplayFrame.model_validate_json(line))
            except Exception as exc:
                raise ValueError(f"invalid replay frame at line {line_number}: {exc}") from exc
    return frames


def built_in_demo_frames() -> list[ReplayFrame]:
    """A safe metadata-only scenario; it does not open a camera or create a real flame."""
    start = datetime(2026, 7, 16, 8, tzinfo=UTC)
    frames: list[ReplayFrame] = []
    for index in range(6):
        for camera_id, role, offset_ms in ((1, "VIEW_A", 0), (2, "VIEW_B", 80)):
            detections = []
            if 1 <= index <= 4:
                detections = [
                    Detection(
                        className="fire",
                        confidence=min(0.95, 0.66 + index * 0.06),
                        bboxXyxy=[300, 220, 430 + index * 4, 390 + index * 3],
                    )
                ]
            frames.append(
                ReplayFrame(
                    cameraId=camera_id,
                    viewRole=role,
                    timestamp=start + timedelta(milliseconds=index * 200 + offset_ms),
                    detections=detections,
                )
            )
    return frames


class MockReplayRunner:
    def __init__(self, *, detector: Detector, pipeline: InferencePipeline) -> None:
        self.detector = detector
        self.pipeline = pipeline

    def run(self, frames: Iterable[ReplayFrame], *, pace: float = 0) -> list[EventEnvelope]:
        emitted: list[EventEnvelope] = []
        previous: datetime | None = None
        self.pipeline.runtime.start()
        try:
            for frame in frames:
                if pace > 0 and previous is not None:
                    delay = max(0, (frame.timestamp - previous).total_seconds() / pace)
                    time.sleep(delay)
                raw = {
                    "detections": [
                        item.model_dump(by_alias=True, mode="json") for item in frame.detections
                    ]
                }
                detections = self.detector.detect([raw])[0]
                emitted.extend(
                    self.pipeline.process(
                        site_id=frame.site_id,
                        zone_id=frame.zone_id,
                        camera_id=frame.camera_id,
                        view_role=frame.view_role,
                        timestamp=frame.timestamp,
                        image_width=frame.image_width,
                        image_height=frame.image_height,
                        detections=detections,
                        process_time_ms=frame.process_time_ms,
                    )
                )
                previous = frame.timestamp
        except Exception:
            self.pipeline.runtime.fail("REPLAY_FAILED")
            raise
        else:
            self.pipeline.runtime.stop()
        return emitted


def write_example(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for frame in built_in_demo_frames():
            handle.write(json.dumps(frame.model_dump(by_alias=True, mode="json")))
            handle.write("\n")
