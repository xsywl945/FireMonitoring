from __future__ import annotations

from pathlib import Path

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
