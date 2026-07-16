from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from time import perf_counter
from uuid import UUID, uuid4

from .contracts import (
    Detection,
    DetectionSummaryPayload,
    EventEnvelope,
    EventType,
    IncidentCandidatePayload,
    IncidentConfirmedPayload,
)
from .fusion import DualCameraFusion, FusionStatus
from .publisher import EventPublisher
from .runtime import RuntimeState
from .temporal import TemporalConfig, TemporalEvidence, TemporalState, TemporalStateMachine


class InferencePipeline:
    """Turns validated per-frame detections into versioned domain events."""

    def __init__(
        self,
        *,
        publisher: EventPublisher,
        source: str,
        model_version: str,
        temporal_config: TemporalConfig | None = None,
        fusion: DualCameraFusion | None = None,
        runtime: RuntimeState | None = None,
    ) -> None:
        self.publisher = publisher
        self.source = source
        self.model_version = model_version
        self.temporal_config = temporal_config or TemporalConfig()
        self.fusion = fusion or DualCameraFusion()
        self.runtime = runtime or RuntimeState(model_version=model_version)
        self._trackers: dict[tuple[int, int, str], TemporalStateMachine] = {}
        self._latest: dict[tuple[int, int, str], TemporalEvidence] = {}
        self._zone_status: dict[int, FusionStatus] = defaultdict(lambda: FusionStatus.NONE)
        self._traces: dict[tuple[int, int, str], UUID] = {}
        self._camera_health: dict[int, bool] = {}
        self._zone_cameras: dict[int, set[int]] = defaultdict(set)

    def set_camera_health(self, camera_id: int, online: bool) -> None:
        self._camera_health[camera_id] = online

    def register_camera(self, zone_id: int, camera_id: int, *, online: bool = False) -> None:
        """Register configured cameras so an offline peer produces a degraded decision."""
        self._zone_cameras[zone_id].add(camera_id)
        self._camera_health[camera_id] = online

    def process(
        self,
        *,
        site_id: int,
        zone_id: int,
        camera_id: int,
        view_role: str,
        timestamp: datetime,
        image_width: int,
        image_height: int,
        detections: list[Detection],
        process_time_ms: float | None = None,
    ) -> list[EventEnvelope]:
        started = perf_counter()
        self._zone_cameras[zone_id].add(camera_id)
        self._camera_health[camera_id] = True
        events: list[EventEnvelope] = []
        process_time = (
            max(0, process_time_ms)
            if process_time_ms is not None
            else (perf_counter() - started) * 1000
        )
        summary = DetectionSummaryPayload(
            frameTimestamp=timestamp,
            imageWidth=image_width,
            imageHeight=image_height,
            detections=detections,
            processTimeMs=process_time,
        )
        events.append(
            EventEnvelope.create(
                event_type=EventType.DETECTION_SUMMARY,
                source=self.source,
                payload=summary,
                occurred_at=timestamp,
                site_id=site_id,
                zone_id=zone_id,
                camera_id=camera_id,
                model_version=self.model_version,
            )
        )

        for class_name in ("fire", "smoke"):
            class_detections = [item for item in detections if item.class_name == class_name]
            strongest = max(class_detections, key=lambda item: item.confidence, default=None)
            area = 0.0
            if strongest is not None:
                x1, y1, x2, y2 = strongest.bbox_xyxy
                area = ((x2 - x1) * (y2 - y1)) / (image_width * image_height)
            tracker_key = (zone_id, camera_id, class_name)
            tracker = self._trackers.get(tracker_key)
            if tracker is None:
                tracker = TemporalStateMachine(
                    camera_id=camera_id,
                    view_role=view_role,
                    class_name=class_name,
                    config=self.temporal_config,
                )
                self._trackers[tracker_key] = tracker
            evidence = tracker.update(
                timestamp=timestamp,
                confidence=strongest.confidence if strongest else None,
                bbox_area=area,
            )
            if evidence is None:
                self._latest.pop(tracker_key, None)
                if tracker.state == TemporalState.NORMAL:
                    self._traces.pop(tracker_key, None)
                continue
            self._latest[tracker_key] = evidence
            trace_id = self._traces.setdefault(tracker_key, uuid4())
            if (
                evidence.state == TemporalState.SUSPECT
                and evidence.transitioned_from == TemporalState.NORMAL
            ):
                candidate = IncidentCandidatePayload(
                    primaryType=class_name.upper(),
                    score=evidence.score,
                    effectiveFrames=evidence.effective_frames,
                    observedAt=evidence.last_seen_at,
                )
                events.append(
                    EventEnvelope.create(
                        event_type=EventType.INCIDENT_CANDIDATE,
                        source=self.source,
                        payload=candidate,
                        trace_id=trace_id,
                        occurred_at=timestamp,
                        site_id=site_id,
                        zone_id=zone_id,
                        camera_id=camera_id,
                        model_version=self.model_version,
                    )
                )

        zone_evidence = [
            item for (item_zone, _, _), item in self._latest.items() if item_zone == zone_id
        ]
        decision = self.fusion.decide(
            zone_evidence,
            camera_health={
                configured_camera_id: self._camera_health.get(configured_camera_id, False)
                for configured_camera_id in self._zone_cameras[zone_id]
            },
            now=timestamp,
        )
        previously = self._zone_status[zone_id]
        if decision.status == FusionStatus.CONFIRMED and previously != FusionStatus.CONFIRMED:
            confirmed_at = decision.confirmed_at or timestamp
            dedup_key = (
                f"zone:{zone_id}:{decision.primary_type}:"
                f"{confirmed_at.isoformat(timespec='milliseconds')}"
            )
            payload = IncidentConfirmedPayload(
                dedupKey=dedup_key,
                primaryType=decision.primary_type,
                severity=decision.severity,
                fusionMode=decision.fusion_mode,
                fusionScore=decision.score,
                startedAt=decision.started_at or timestamp,
                confirmedAt=confirmed_at,
                observations=list(decision.observations),
            )
            first_observation = decision.observations[0]
            trace_id = self._traces.get(
                (zone_id, first_observation.camera_id, first_observation.class_name), uuid4()
            )
            events.append(
                EventEnvelope.create(
                    event_type=EventType.INCIDENT_CONFIRMED,
                    source=self.source,
                    payload=payload,
                    trace_id=trace_id,
                    occurred_at=confirmed_at,
                    site_id=site_id,
                    zone_id=zone_id,
                    camera_id=(
                        first_observation.camera_id
                        if decision.fusion_mode == "SINGLE_CAMERA"
                        else None
                    ),
                    model_version=self.model_version,
                )
            )
        self._zone_status[zone_id] = decision.status

        for event in events:
            self.publisher.publish(event)
        confirmed = any(event.event_type == EventType.INCIDENT_CONFIRMED for event in events)
        self.runtime.record_frame(timestamp, len(events), confirmed)
        return events
