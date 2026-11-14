from __future__ import annotations

from typing import Protocol


class VisionReasoner(Protocol):
    def analyze(self, *, incident_id: int | None, images: list):
        """Return a validated evidence call. Do not choose an extinguishing action."""
