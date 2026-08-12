from __future__ import annotations

import base64
import logging
import queue
import threading
from dataclasses import dataclass

from .contracts import (
    Detection,
    EventEnvelope,
    EventType,
    EvidenceFrame,
    IncidentEvidenceReadyPayload,
    StrictModel,
    VlmAnalysisPayload,
    utc_now,
)
from .evidence import EvidenceStore
from .frames import FramePacket
from .live_frames import encode_jpeg
from .publisher import EventPublisher
from .runtime import RuntimeState
from .vision.base import VisionReasoner

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IncidentEnrichmentJob:
    confirmed: EventEnvelope
    frame: FramePacket
    detections: list[Detection]
    context_frames: tuple[FramePacket, ...] = ()


class IncidentEnrichmentWorker:
    """Bounded post-confirmation worker for evidence and optional cloud semantics."""

    def __init__(
        self,
        *,
        publisher: EventPublisher,
        evidence_store: EvidenceStore,
        reasoner: VisionReasoner,
        cv2_module: object,
        capacity: int = 4,
        gate_confirmed: bool = False,
        gate_min_confidence: float = 0.7,
        gate_fail_open: bool = False,
        runtime: RuntimeState | None = None,
    ) -> None:
        self.publisher = publisher
        self.evidence_store = evidence_store
        self.reasoner = reasoner
        self._cv2 = cv2_module
        self.gate_confirmed = gate_confirmed
        self.gate_min_confidence = gate_min_confidence
        self.gate_fail_open = gate_fail_open
        self.runtime = runtime
        self._jobs: queue.Queue[IncidentEnrichmentJob | None] = queue.Queue(maxsize=capacity)
        self._thread = threading.Thread(target=self._run, name="incident-enrichment", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def submit(self, job: IncidentEnrichmentJob) -> bool:
        try:
            self._jobs.put_nowait(job)
            return True
        except queue.Full:
            log.error("incident enrichment queue is full; traceId=%s", job.confirmed.trace_id)
            return False

    def stop(self, *, timeout: float = 5.0) -> None:
        try:
            self._jobs.put_nowait(None)
        except queue.Full:
            return
        self._thread.join(timeout=timeout)

    def process(self, job: IncidentEnrichmentJob) -> list[EventEnvelope]:
        frames = job.context_frames[-3:] if job.context_frames else (job.frame,)
        encoded_frames = [encode_jpeg(self._cv2, frame.image) for frame in frames]
        jpeg = encoded_frames[-1]
        image_urls = [
            "data:image/jpeg;base64," + base64.b64encode(item).decode("ascii")
            for item in encoded_frames
        ]
        judgement = self.reasoner.analyze(incident_id=None, image_data_urls=image_urls)

        gated_events: list[EventEnvelope] = []
        if self.gate_confirmed:
            if self._accepted_by_gate(judgement):
                self.publisher.publish(job.confirmed)
                gated_events.append(job.confirmed)
            elif judgement.status != "SUCCEEDED" and self.gate_fail_open:
                log.error(
                    "VLM gate unavailable; fail-open alert emitted: traceId=%s error=%s",
                    job.confirmed.trace_id,
                    judgement.error_code,
                )
                self.publisher.publish(job.confirmed)
                gated_events.append(job.confirmed)
            else:
                log.warning(
                    "VLM gate held candidate: traceId=%s status=%s visibleFire=%s "
                    "visibleSmoke=%s confidence=%s error=%s",
                    job.confirmed.trace_id,
                    judgement.status,
                    judgement.has_visible_fire,
                    judgement.has_visible_smoke,
                    judgement.confidence,
                    judgement.error_code,
                )
                return []

        object_key: str | None = None
        try:
            object_key = self.evidence_store.put_jpeg(
                trace_id=job.confirmed.trace_id,
                captured_at=job.frame.captured_at.isoformat(),
                data=jpeg,
            )
        except Exception:
            log.exception("could not store incident evidence; traceId=%s", job.confirmed.trace_id)

        observations = job.confirmed.payload.get("observations") or []
        temporal_score = float(observations[0].get("score", 0)) if observations else 0.0
        evidence_payload = IncidentEvidenceReadyPayload(
            evidence=[
                EvidenceFrame(
                    cameraId=job.frame.camera_id,
                    viewRole="SINGLE",
                    capturedAt=job.frame.captured_at,
                    imageWidth=job.frame.width,
                    imageHeight=job.frame.height,
                    detections=job.detections,
                    temporalScore=temporal_score,
                    snapshotObjectKey=object_key,
                )
            ]
        )
        evidence_event = self._related_event(
            job.confirmed,
            event_type=EventType.INCIDENT_EVIDENCE_READY,
            payload=evidence_payload,
        )
        self.publisher.publish(evidence_event)

        vlm_type = (
            EventType.VLM_ANALYSIS_COMPLETED
            if judgement.status == "SUCCEEDED"
            else EventType.VLM_ANALYSIS_FAILED
        )
        vlm_event = self._related_event(job.confirmed, event_type=vlm_type, payload=judgement)
        self.publisher.publish(vlm_event)
        events = [*gated_events, evidence_event, vlm_event]
        if self.runtime is not None:
            self.runtime.record_events(len(events), confirmed=bool(gated_events))
        return events

    def _accepted_by_gate(self, judgement: VlmAnalysisPayload) -> bool:
        confidence = judgement.confidence
        return bool(
            judgement.status == "SUCCEEDED"
            and (judgement.has_visible_fire or judgement.has_visible_smoke)
            and confidence is not None
            and confidence >= self.gate_min_confidence
        )

    def _run(self) -> None:
        while True:
            job = self._jobs.get()
            try:
                if job is None:
                    return
                self.process(job)
            except Exception:
                log.exception("incident enrichment failed")
            finally:
                self._jobs.task_done()

    @staticmethod
    def _related_event(
        confirmed: EventEnvelope, *, event_type: EventType, payload: StrictModel
    ) -> EventEnvelope:
        return EventEnvelope.create(
            event_type=event_type,
            source=confirmed.source,
            payload=payload,
            trace_id=confirmed.trace_id,
            occurred_at=utc_now(),
            site_id=confirmed.site_id,
            zone_id=confirmed.zone_id,
            camera_id=confirmed.camera_id,
            model_version=confirmed.model_version,
        )
