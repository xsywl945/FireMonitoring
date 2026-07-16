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
