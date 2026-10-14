from datetime import UTC, datetime, timedelta

import pytest

from fire_monitoring_inference.contracts import Detection, EventType
from fire_monitoring_inference.frames import FramePacket
from fire_monitoring_inference.live import LiveCameraConfig, LiveCameraRunner
from fire_monitoring_inference.pipeline import InferencePipeline
from fire_monitoring_inference.publisher import MemoryEventPublisher
from fire_monitoring_inference.runtime import RuntimeState


class FakeSource:
    def __init__(self, count: int) -> None:
        started = datetime(2026, 8, 12, tzinfo=UTC)
        self.frames = [
            FramePacket(
                camera_id=1,
                captured_at=started + timedelta(milliseconds=index * 200),
                monotonic_ns=index,
                image=object(),
                width=1280,
                height=720,
            )
            for index in range(count)
        ]
        self.released = False

    def read(self) -> FramePacket:
        return self.frames.pop(0)

    def release(self) -> None:
        self.released = True


class FakeDetector:
    model_version = "test-model"

    def detect(self, images: list[object]) -> list[list[Detection]]:
        return [
            [
                Detection(
                    className="fire",
                    confidence=0.8,
                    bboxXyxy=[100, 100, 200, 220],
                )
            ]
            for _ in images
        ]


def test_live_camera_runner_reuses_pipeline_and_releases_camera() -> None:
    source = FakeSource(2)
    publisher = MemoryEventPublisher()
    runtime = RuntimeState(model_version="test-model")
    pipeline = InferencePipeline(
        publisher=publisher,
        source="test-live-worker",
        model_version="test-model",
        runtime=runtime,
    )

    summary = LiveCameraRunner(
        source=source,
        detector=FakeDetector(),
        pipeline=pipeline,
        config=LiveCameraConfig(target_fps=0, max_frames=2),
    ).run()

    assert source.released is True
    assert summary.frames_processed == 2
    assert summary.events_published == len(publisher.events)
    assert summary.stopped_by_user is False
    assert runtime.snapshot()["status"] == "STOPPED"
    assert [event.event_type for event in publisher.events].count(EventType.DETECTION_SUMMARY) == 2


def test_live_camera_runner_marks_failure_and_releases_camera() -> None:
    source = FakeSource(1)
    runtime = RuntimeState(model_version="test-model")
    pipeline = InferencePipeline(
        publisher=MemoryEventPublisher(),
        source="test-live-worker",
        model_version="test-model",
        runtime=runtime,
    )

    class BrokenDetector(FakeDetector):
        def detect(self, images: list[object]) -> list[list[Detection]]:
            return []

    with pytest.raises(RuntimeError, match="exactly one"):
        LiveCameraRunner(
            source=source,
            detector=BrokenDetector(),
            pipeline=pipeline,
            config=LiveCameraConfig(target_fps=0, max_frames=1),
        ).run()

    assert source.released is True
    assert runtime.snapshot()["status"] == "FAILED"


def test_stopped_camera_releases_device_without_reading_a_frame() -> None:
    import threading

    source = FakeSource(1)
    stop = threading.Event()
    stop.set()
    runtime = RuntimeState(model_version="test-model")
    pipeline = InferencePipeline(
        publisher=MemoryEventPublisher(), source="test", model_version="test", runtime=runtime,
    )
    LiveCameraRunner(
        source=source, detector=FakeDetector(), pipeline=pipeline,
        config=LiveCameraConfig(), stop_event=stop,
    ).run()
    assert source.released
    assert len(source.frames) == 1
