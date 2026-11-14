from __future__ import annotations

import base64

from fire_monitoring_inference.vision.qwen import QwenVisionReasoner

from ..config import AppConfig


class QwenAnalyzer:
    def __init__(self, config: AppConfig) -> None:
        self._reasoner = QwenVisionReasoner(
            api_key=config.llm.api_key or None,
            base_url=config.llm.base_url,
            model=config.llm.model,
        )

    def analyze(self, alert_id: int, jpegs: list[bytes]) -> dict:
        urls = [
            "data:image/jpeg;base64," + base64.b64encode(blob).decode("ascii") for blob in jpegs
        ]
        payload = self._reasoner.analyze(incident_id=alert_id, image_data_urls=urls)
        return {
            "status": payload.status,
            "provider": payload.provider,
            "model": payload.model,
            "prompt_version": payload.prompt_version,
            "has_visible_fire": payload.has_visible_fire,
            "has_visible_smoke": payload.has_visible_smoke,
            "source_nature": payload.source_nature,
            "scene_type": payload.scene_type,
            "burning_objects": list(payload.burning_objects),
            "people_at_risk": payload.people_at_risk,
            "risk_level": payload.risk_level,
            "reasoning_summary": payload.reasoning_summary,
            "recommended_actions": list(payload.recommended_actions),
            "confidence": payload.confidence,
            "uncertainties": list(payload.uncertainties),
            "error_code": payload.error_code,
        }
