from fire_monitoring_inference.contracts import EventType
from fire_monitoring_inference.detectors.mock import MockDetector
from fire_monitoring_inference.pipeline import InferencePipeline
from fire_monitoring_inference.publisher import MemoryEventPublisher
from fire_monitoring_inference.replay import MockReplayRunner, built_in_demo_frames
from fire_monitoring_inference.temporal import TemporalConfig


def test_mock_replay_emits_detection_candidate_and_confirmed_events() -> None:
    publisher = MemoryEventPublisher()
    pipeline = InferencePipeline(
        publisher=publisher,
        source="test-worker",
        model_version="mock-test",
        temporal_config=TemporalConfig(n=3, m=5, candidate_n=1, cooldown_ms=1000),
    )
    events = MockReplayRunner(detector=MockDetector(), pipeline=pipeline).run(
        built_in_demo_frames()
    )
    types = [event.event_type for event in events]

    assert types.count(EventType.DETECTION_SUMMARY) == len(built_in_demo_frames())
    assert EventType.INCIDENT_CANDIDATE in types
    assert types.count(EventType.INCIDENT_CONFIRMED) == 1
    confirmed = next(event for event in events if event.event_type == EventType.INCIDENT_CONFIRMED)
    assert confirmed.payload["fusionMode"] == "DUAL_CAMERA"
    assert 0 <= confirmed.payload["fusionScore"] <= 1
    assert publisher.events == events


def test_pipeline_can_defer_confirmed_event_for_vlm_gate() -> None:
    publisher = MemoryEventPublisher()
    pipeline = InferencePipeline(
        publisher=publisher,
        source="test-worker",
        model_version="mock-test",
        temporal_config=TemporalConfig(n=3, m=5, candidate_n=1, cooldown_ms=1000),
        defer_confirmed=True,
    )

    events = MockReplayRunner(detector=MockDetector(), pipeline=pipeline).run(
        built_in_demo_frames()
    )

    assert any(event.event_type == EventType.INCIDENT_CONFIRMED for event in events)
    assert all(event.event_type != EventType.INCIDENT_CONFIRMED for event in publisher.events)
    assert pipeline.runtime.snapshot()["incidentsConfirmed"] == 0
    assert pipeline.runtime.snapshot()["eventsPublished"] == len(publisher.events)


def test_zero_cooldown_rearms_with_new_trace_after_fire_clears():
    from datetime import timedelta

    from fire_monitoring_inference.contracts import Detection, utc_now

    publisher = MemoryEventPublisher()
    pipeline = InferencePipeline(
        publisher=publisher, source="test", model_version="test", fire_only=True
    )
    start = utc_now()
    for index in range(9):
        events = pipeline.process(
            site_id=1, zone_id=2, camera_id=3, view_role="SINGLE",
            timestamp=start + timedelta(milliseconds=index * 200),
            image_width=640, image_height=480,
            detections=[] if 3 <= index < 6 else [
                Detection(className="fire", confidence=0.9, bboxXyxy=[10, 10, 50, 50])
            ],
        )
        if index == 5:
            assert not any(e.event_type == EventType.INCIDENT_CONFIRMED for e in events)
    confirmed = [e for e in publisher.events if e.event_type == EventType.INCIDENT_CONFIRMED]
    assert len(confirmed) == 2
    assert confirmed[0].trace_id != confirmed[1].trace_id


def test_local_fire_mode_does_not_let_stronger_smoke_hide_later_flames():
    from datetime import timedelta

    from fire_monitoring_inference.contracts import Detection, utc_now

    publisher = MemoryEventPublisher()
    pipeline = InferencePipeline(
        publisher=publisher, source="live-test", model_version="test", fire_only=True
    )
    start = utc_now()
    for index in range(6):
        detections = [Detection(className="smoke", confidence=0.99, bboxXyxy=[10, 10, 50, 50])]
        if index >= 3:
            detections.append(
                Detection(className="fire", confidence=0.8, bboxXyxy=[10, 10, 50, 50])
            )
        pipeline.process(
            site_id=1,
            zone_id=2,
            camera_id=3,
            view_role="SINGLE",
            timestamp=start + timedelta(milliseconds=index * 200),
            image_width=640,
            image_height=480,
            detections=detections,
        )
    confirmed = [e for e in publisher.events if e.event_type == EventType.INCIDENT_CONFIRMED]
    assert len(confirmed) == 1
    assert confirmed[0].payload["primaryType"] == "FIRE"
    assert confirmed[0].payload["observations"][0]["effectiveFrames"] == 3
