from __future__ import annotations

from typing import Any, Protocol

from ..contracts import Detection


class Detector(Protocol):
    model_version: str

    def detect(self, images: list[Any]) -> list[list[Detection]]:
        """Run a batch and return one validated detection list per input image."""
