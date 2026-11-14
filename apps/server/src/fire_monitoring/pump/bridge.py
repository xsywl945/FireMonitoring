from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fire_monitoring_inference.contracts import (
    EventEnvelope,
    EventType,
    FusionObservation,
    IncidentConfirmedPayload,
    VlmAnalysisPayload,
)
from fire_monitoring_inference.pump import PumpConfig, PumpController

from ..config import AppConfig


def build_pump(config: AppConfig, transport=None) -> PumpController:
    settings = config.pump
    pump_config = PumpConfig(
        enabled=settings.enabled,
        port=settings.serial_port,
        zone_id=settings.zone_id,
        duration_ms=settings.duration_ms,
        cooldown_seconds=settings.cooldown_seconds,
        min_confidence=settings.min_confidence,
        max_evidence_age_seconds=settings.max_evidence_age_seconds,
        require_vlm=settings.require_vlm,
        local_min_confidence=settings.local_min_confidence,
        local_min_frames=settings.local_min_frames,
    )
    return PumpController(
        config=pump_config,
        journal_path=Path(settings.journal_path),
        transport=transport,
    )


def trigger_pump(
    controller,
    *,
    room_id: int,
    alert_type: str,
    observations: list[dict],
    analysis: dict | None,
    captured_at: datetime,
    model_version: str,
) -> None:
    chosen = sorted(observations, key=lambda item: item["score"], reverse=True)[:2]
    payload = IncidentConfirmedPayload(
        dedupKey=f"room:{room_id}:{alert_type}:{captured_at.isoformat()}",
        primaryType=alert_type,
        severity="HIGH",
        fusionMode="DUAL_CAMERA" if len(chosen) > 1 else "SINGLE_CAMERA",
        fusionScore=max(item["score"] for item in chosen),
        startedAt=captured_at,
        confirmedAt=captured_at,
        observations=[
            FusionObservation(
                cameraId=item["camera_id"],
                viewRole="SINGLE",
                className=item["class_name"],
                score=item["score"],
                effectiveFrames=item["effective_frames"],
                durationMs=item["duration_ms"],
            )
            for item in chosen
        ],
    )
    event = EventEnvelope.create(
        event_type=EventType.INCIDENT_CONFIRMED,
        source="fire-monitoring",
        payload=payload,
        occurred_at=captured_at,
        zone_id=room_id,
        camera_id=chosen[0]["camera_id"],
        model_version=model_version,
    )
    judgement = None
    if analysis is not None:
        judgement = VlmAnalysisPayload(
            status=analysis["status"],
            provider=analysis["provider"],
            model=analysis["model"],
            promptVersion=analysis["prompt_version"],
            hasVisibleFire=analysis["has_visible_fire"],
            hasVisibleSmoke=analysis["has_visible_smoke"],
            waterProhibited=analysis["water_prohibited"],
            errorCode=analysis.get("error_code"),
        )
    controller.trigger(event, judgement, captured_at=captured_at)
