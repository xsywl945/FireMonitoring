from __future__ import annotations

from fire_monitoring_inference.vision.qwen import PROMPT_VERSION


class CachedAnalyzer:
    serves_offline = True

    def __init__(self, document: dict, model: str) -> None:
        if "evidence" not in document:
            raise RuntimeError("千问缓存没有 evidence")
        self.document = document
        self.model = model

    def analyze(self, alert_id: int, frames: list, before: bytes | None, after: bytes | None) -> dict:
        del alert_id, frames, before, after
        note = self.document.get("note") or "缓存结果"
        return {
            "status": "SUCCEEDED",
            "provider": "cache",
            "model": self.model,
            "prompt_version": PROMPT_VERSION,
            "evidence": self.document["evidence"],
            "error_code": None,
            "cached": True,
            "synthetic": bool(self.document.get("synthetic") or self.document.get("handwritten")),
            "cache_note": note,
        }
