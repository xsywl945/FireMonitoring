from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
    )


class EventType(StrEnum):
    CAMERA_HEALTH_CHANGED = "CAMERA_HEALTH_CHANGED"
    DETECTION_SUMMARY = "DETECTION_SUMMARY"
    INCIDENT_CANDIDATE = "INCIDENT_CANDIDATE"
    INCIDENT_CONFIRMED = "INCIDENT_CONFIRMED"
    INCIDENT_EVIDENCE_READY = "INCIDENT_EVIDENCE_READY"
    VLM_ANALYSIS_COMPLETED = "VLM_ANALYSIS_COMPLETED"
    VLM_ANALYSIS_FAILED = "VLM_ANALYSIS_FAILED"
    TASK_RUNTIME_CHANGED = "TASK_RUNTIME_CHANGED"
    ALGORITHM_DEGRADED = "ALGORITHM_DEGRADED"


class Detection(StrictModel):
    class_name: Literal["fire", "smoke"] = Field(alias="className")
    confidence: float = Field(ge=0, le=1)
    bbox_xyxy: tuple[
        Annotated[float, Field(ge=0)],
        Annotated[float, Field(ge=0)],
        Annotated[float, Field(ge=0)],
        Annotated[float, Field(ge=0)],
    ] = Field(alias="bboxXyxy")

    @model_validator(mode="after")
    def validate_box(self) -> Detection:
        x1, y1, x2, y2 = self.bbox_xyxy
        if x2 < x1 or y2 < y1:
            raise ValueError("bboxXyxy must be ordered as x1, y1, x2, y2")
        return self


class DetectionSummaryPayload(StrictModel):
    frame_timestamp: datetime = Field(alias="frameTimestamp")
    image_width: int = Field(alias="imageWidth", ge=1)
    image_height: int = Field(alias="imageHeight", ge=1)
    detections: list[Detection] = Field(max_length=100)
    process_time_ms: float = Field(alias="processTimeMs", ge=0)


class FusionObservation(StrictModel):
    camera_id: int = Field(alias="cameraId", ge=1)
    view_role: Literal["VIEW_A", "VIEW_B", "SINGLE"] = Field(alias="viewRole")
    class_name: Literal["fire", "smoke"] = Field(alias="className")
    score: float = Field(ge=0, le=1)
    effective_frames: int = Field(alias="effectiveFrames", ge=1)
    duration_ms: int = Field(alias="durationMs", ge=0)
    snapshot_object_key: str | None = Field(default=None, alias="snapshotObjectKey")


class IncidentConfirmedPayload(StrictModel):
    dedup_key: str = Field(alias="dedupKey", min_length=1, max_length=200)
    primary_type: Literal["FIRE", "SMOKE", "FIRE_AND_SMOKE"] = Field(alias="primaryType")
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    fusion_mode: Literal["SINGLE_CAMERA", "DUAL_CAMERA"] = Field(alias="fusionMode")
    fusion_score: float = Field(alias="fusionScore", ge=0, le=1)
    started_at: datetime = Field(alias="startedAt")
    confirmed_at: datetime = Field(alias="confirmedAt")
    observations: list[FusionObservation] = Field(min_length=1, max_length=2)


class IncidentCandidatePayload(StrictModel):
    primary_type: Literal["FIRE", "SMOKE"] = Field(alias="primaryType")
    score: float = Field(ge=0, le=1)
    state: Literal["SUSPECT"] = "SUSPECT"
    effective_frames: int = Field(alias="effectiveFrames", ge=1)
    observed_at: datetime = Field(alias="observedAt")


class VlmAnalysisPayload(StrictModel):
    incident_id: int = Field(alias="incidentId", ge=1)
    status: Literal["SUCCEEDED", "FAILED", "DEMO_FALLBACK"]
    provider: str
    model: str
    prompt_version: str = Field(alias="promptVersion")
    has_visible_fire: bool | None = Field(default=None, alias="hasVisibleFire")
    has_visible_smoke: bool | None = Field(default=None, alias="hasVisibleSmoke")
    source_nature: Literal["electrical", "open_flame", "chemical", "cooking", "unknown"] | None = (
        Field(default=None, alias="sourceNature")
    )
    scene_type: Literal["classroom", "laboratory", "corridor", "other"] | None = Field(
        default=None, alias="sceneType"
    )
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] | None = Field(
        default=None, alias="riskLevel"
    )
    reasoning_summary: str | None = Field(default=None, alias="reasoningSummary", max_length=1000)
    recommended_actions: list[Annotated[str, Field(max_length=100)]] = Field(
        default_factory=list, alias="recommendedActions", max_length=10
    )
    confidence: float | None = Field(default=None, ge=0, le=1)
    uncertainties: list[Annotated[str, Field(max_length=200)]] = Field(
        default_factory=list, max_length=10
    )
    error_code: str | None = Field(default=None, alias="errorCode")
    latency_ms: float | None = Field(default=None, alias="latencyMs", ge=0)


Payload = dict[str, Any] | StrictModel


class EventEnvelope(StrictModel):
    event_id: UUID = Field(default_factory=uuid4, alias="eventId")
    event_type: EventType = Field(alias="eventType")
    schema_version: Literal["1.0"] = Field(default="1.0", alias="schemaVersion")
    occurred_at: datetime = Field(default_factory=utc_now, alias="occurredAt")
    trace_id: UUID = Field(default_factory=uuid4, alias="traceId")
    source: str = Field(min_length=1, max_length=100)
    site_id: int | None = Field(default=None, alias="siteId", ge=1)
    zone_id: int | None = Field(default=None, alias="zoneId", ge=1)
    camera_id: int | None = Field(default=None, alias="cameraId", ge=1)
    model_version: str | None = Field(default=None, alias="modelVersion", max_length=100)
    payload: dict[str, Any]

    @field_validator("occurred_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurredAt must include a timezone")
        return value

    @classmethod
    def create(
        cls,
        *,
        event_type: EventType,
        source: str,
        payload: Payload,
        trace_id: UUID | None = None,
        occurred_at: datetime | None = None,
        site_id: int | None = None,
        zone_id: int | None = None,
        camera_id: int | None = None,
        model_version: str | None = None,
    ) -> EventEnvelope:
        payload_dict = (
            payload.model_dump(by_alias=True, mode="json", exclude_none=True)
            if isinstance(payload, StrictModel)
            else payload
        )
        return cls(
            eventType=event_type,
            source=source,
            payload=payload_dict,
            traceId=trace_id or uuid4(),
            occurredAt=occurred_at or utc_now(),
            siteId=site_id,
            zoneId=zone_id,
            cameraId=camera_id,
            modelVersion=model_version,
        )

    def to_wire(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json", exclude_none=True)
