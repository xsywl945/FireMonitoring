from datetime import UTC, datetime
from uuid import UUID

from fire_monitoring_inference.contracts import (
    Detection,
    EventEnvelope,
    EventType,
    VlmAnalysisPayload,
)
from fire_monitoring_inference.enrichment import (
    IncidentEnrichmentJob,
    IncidentEnrichmentWorker,
)
from fire_monitoring_inference.frames import FramePacket
from fire_monitoring_inference.publisher import MemoryEventPublisher
from fire_monitoring_inference.runtime import RuntimeState


class FakeCv2:
    IMWRITE_JPEG_QUALITY = 1

    @staticmethod
    def imencode(extension: str, image: object, parameters: list[int]) -> tuple[bool, bytearray]:
        assert extension == ".jpg"
        assert image is not None
        assert parameters == [1, 85]
        return True, bytearray(b"jpeg-evidence")


class FakeEvidenceStore:
    def __init__(self) -> None:
        self.data: bytes | None = None

    def put_jpeg(self, *, trace_id: UUID, captured_at: str, data: bytes) -> str:
        assert trace_id
        assert captured_at
        self.data = data
        return f"incidents/{trace_id}/frame.jpg"


class FakeReasoner:
    def __init__(self) -> None:
        self.image_count = 0

    def analyze(self, *, incident_id: int | None, image_data_urls: list[str]) -> VlmAnalysisPayload:
        assert incident_id is None
        assert image_data_urls[0].startswith("data:image/jpeg;base64,")
        self.image_count = len(image_data_urls)
        return VlmAnalysisPayload(
            status="SUCCEEDED",
            provider="dashscope",
            model="qwen3.7-plus",
            promptVersion="fire-risk-v2",
            hasVisibleFire=True,
            hasVisibleSmoke=False,
            sourceNature="open_flame",
            sceneType="classroom",
            riskLevel="HIGH",
            reasoningSummary="Visible flame.",
            recommendedActions=["Verify the scene"],
            confidence=0.8,
            uncertainties=[],
        )


def test_enrichment_publishes_evidence_then_vlm_with_same_trace() -> None:
    timestamp = datetime(2026, 8, 12, tzinfo=UTC)
    confirmed = EventEnvelope.create(
        event_type=EventType.INCIDENT_CONFIRMED,
        source="test-worker",
        payload={"observations": [{"score": 0.84}]},
        occurred_at=timestamp,
        site_id=1,
        zone_id=2,
        camera_id=3,
        model_version="test-model",
    )
    detection = Detection(className="fire", confidence=0.9, bboxXyxy=[10, 20, 100, 120])
    frame = FramePacket(
        camera_id=3,
        captured_at=timestamp,
        monotonic_ns=1,
        image=object(),
        width=640,
        height=480,
    )
    publisher = MemoryEventPublisher()
    evidence_store = FakeEvidenceStore()
    worker = IncidentEnrichmentWorker(
        publisher=publisher,
        evidence_store=evidence_store,
        reasoner=FakeReasoner(),
        cv2_module=FakeCv2(),
    )

    events = worker.process(
        IncidentEnrichmentJob(confirmed=confirmed, frame=frame, detections=[detection])
    )

    assert [event.event_type for event in events] == [
        EventType.INCIDENT_EVIDENCE_READY,
        EventType.VLM_ANALYSIS_COMPLETED,
    ]
    assert all(event.trace_id == confirmed.trace_id for event in events)
    assert events[0].payload["evidence"][0]["snapshotObjectKey"].startswith("incidents/")
    assert events[1].payload["model"] == "qwen3.7-plus"
    assert evidence_store.data == b"jpeg-evidence"
    assert publisher.events == events


class NegativeReasoner:
    def analyze(self, *, incident_id: int | None, image_data_urls: list[str]) -> VlmAnalysisPayload:
        return VlmAnalysisPayload(
            status="SUCCEEDED",
            provider="dashscope",
            model="qwen3.7-plus",
            promptVersion="fire-risk-v3",
            hasVisibleFire=False,
            hasVisibleSmoke=False,
            sourceNature="unknown",
            sceneType="classroom",
            riskLevel="LOW",
            reasoningSummary="Only a screen depiction is visible.",
            recommendedActions=[],
            confidence=0.95,
            uncertainties=[],
        )


class FailedReasoner:
    def analyze(self, *, incident_id: int | None, image_data_urls: list[str]) -> VlmAnalysisPayload:
        return VlmAnalysisPayload(
            status="FAILED",
            provider="dashscope",
            model="qwen3.7-plus",
            promptVersion="fire-risk-v3",
            recommendedActions=[],
            uncertainties=["cloud_semantic_analysis_unavailable"],
            errorCode="VLM_TIMEOUT",
        )


def _gate_job() -> IncidentEnrichmentJob:
    timestamp = datetime(2026, 8, 12, tzinfo=UTC)
    confirmed = EventEnvelope.create(
        event_type=EventType.INCIDENT_CONFIRMED,
        source="test-worker",
        payload={"observations": [{"score": 0.84}]},
        occurred_at=timestamp,
        site_id=1,
        zone_id=2,
        camera_id=3,
        model_version="test-model",
    )
    detection = Detection(className="fire", confidence=0.9, bboxXyxy=[10, 20, 100, 120])
    frames = tuple(
        FramePacket(
            camera_id=3,
            captured_at=timestamp,
            monotonic_ns=index,
            image=object(),
            width=640,
            height=480,
        )
        for index in range(3)
    )
    return IncidentEnrichmentJob(
        confirmed=confirmed,
        frame=frames[-1],
        detections=[detection],
        context_frames=frames,
    )


def test_vlm_gate_publishes_confirmed_first_after_positive_three_frame_review() -> None:
    publisher = MemoryEventPublisher()
    reasoner = FakeReasoner()
    runtime = RuntimeState(model_version="test-model")
    worker = IncidentEnrichmentWorker(
        publisher=publisher,
        evidence_store=FakeEvidenceStore(),
        reasoner=reasoner,
        cv2_module=FakeCv2(),
        gate_confirmed=True,
        gate_min_confidence=0.7,
        runtime=runtime,
    )

    events = worker.process(_gate_job())

    assert reasoner.image_count == 3
    assert [event.event_type for event in events] == [
        EventType.INCIDENT_CONFIRMED,
        EventType.INCIDENT_EVIDENCE_READY,
        EventType.VLM_ANALYSIS_COMPLETED,
    ]
    assert publisher.events == events
    assert runtime.snapshot()["eventsPublished"] == 3
    assert runtime.snapshot()["incidentsConfirmed"] == 1


def test_vlm_gate_holds_negative_or_low_quality_candidate() -> None:
    publisher = MemoryEventPublisher()
    store = FakeEvidenceStore()
    worker = IncidentEnrichmentWorker(
        publisher=publisher,
        evidence_store=store,
        reasoner=NegativeReasoner(),
        cv2_module=FakeCv2(),
        gate_confirmed=True,
    )

    assert worker.process(_gate_job()) == []
    assert publisher.events == []
    assert store.data is None


def test_vlm_gate_failure_is_strict_by_default_but_can_fail_open() -> None:
    strict_publisher = MemoryEventPublisher()
    strict_worker = IncidentEnrichmentWorker(
        publisher=strict_publisher,
        evidence_store=FakeEvidenceStore(),
        reasoner=FailedReasoner(),
        cv2_module=FakeCv2(),
        gate_confirmed=True,
    )
    assert strict_worker.process(_gate_job()) == []
    assert strict_publisher.events == []

    fallback_publisher = MemoryEventPublisher()
    fallback_worker = IncidentEnrichmentWorker(
        publisher=fallback_publisher,
        evidence_store=FakeEvidenceStore(),
        reasoner=FailedReasoner(),
        cv2_module=FakeCv2(),
        gate_confirmed=True,
        gate_fail_open=True,
    )
    events = fallback_worker.process(_gate_job())
    assert [event.event_type for event in events] == [
        EventType.INCIDENT_CONFIRMED,
        EventType.INCIDENT_EVIDENCE_READY,
        EventType.VLM_ANALYSIS_FAILED,
    ]
