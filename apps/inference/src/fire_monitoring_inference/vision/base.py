from __future__ import annotations

from typing import Protocol

from ..contracts import VlmAnalysisPayload


class VisionReasoner(Protocol):
    def analyze(self, *, incident_id: int, image_data_urls: list[str]) -> VlmAnalysisPayload:
        """Analyze one incident without changing whether the incident is confirmed."""
