import json
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from fire_monitoring_inference.contracts import (
    Detection,
    DetectionSummaryPayload,
    EventEnvelope,
    EventType,
    FusionObservation,
    IncidentConfirmedPayload,
    VlmAnalysisPayload,
)

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "contracts" / "events" / "v1"


def validate(schema_path: Path, instance: dict) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(instance)


def test_detection_envelope_matches_shared_json_schemas() -> None:
    timestamp = datetime(2026, 7, 16, tzinfo=UTC)
    payload = DetectionSummaryPayload(
        frameTimestamp=timestamp,
        imageWidth=1280,
        imageHeight=720,
        processTimeMs=18.5,
        detections=[Detection(className="smoke", confidence=0.81, bboxXyxy=[1, 2, 30, 40])],
    )
    event = EventEnvelope.create(
        event_type=EventType.DETECTION_SUMMARY,
        source="test-worker",
        payload=payload,
        occurred_at=timestamp,
        site_id=1,
        zone_id=1,
        camera_id=1,
        model_version="test-model",
    ).to_wire()

    validate(CONTRACTS / "event-envelope.schema.json", event)
    validate(CONTRACTS / "payloads" / "detection-summary.schema.json", event["payload"])


def test_incident_and_vlm_payloads_match_shared_json_schemas() -> None:
    timestamp = datetime(2026, 7, 16, tzinfo=UTC)
    incident = IncidentConfirmedPayload(
        dedupKey="zone:1:FIRE:test",
        primaryType="FIRE",
        severity="HIGH",
        fusionMode="SINGLE_CAMERA",
        fusionScore=0.83,
        startedAt=timestamp,
        confirmedAt=timestamp,
        observations=[
            FusionObservation(
                cameraId=1,
                viewRole="SINGLE",
                className="fire",
                score=0.83,
                effectiveFrames=3,
                durationMs=400,
            )
        ],
    )
    validate(
        CONTRACTS / "payloads" / "incident-confirmed.schema.json",
        incident.model_dump(by_alias=True, mode="json", exclude_none=True),
    )

    fallback = VlmAnalysisPayload(
        incidentId=1,
        status="FAILED",
        provider="dashscope",
        model="qwen3-vl-plus",
        promptVersion="fire-risk-v1",
        recommendedActions=[],
        uncertainties=["cloud_semantic_analysis_unavailable"],
        errorCode="VLM_TIMEOUT",
        latencyMs=25,
    )
    validate(
        CONTRACTS / "payloads" / "vlm-analysis.schema.json",
        fallback.model_dump(by_alias=True, mode="json", exclude_none=True),
    )
