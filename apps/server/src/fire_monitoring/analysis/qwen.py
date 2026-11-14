from __future__ import annotations

import base64

from fire_monitoring_inference.analysis.images import enlarge_crop
from fire_monitoring_inference.vision.qwen import (
    PROMPT_VERSION,
    PromptImage,
    QwenVisionReasoner,
)

from ..config import AppConfig

ROLE_ORDER = ("keyframe", "crop", "before", "after")


def prompt_images(
    frames: list,
    before: bytes | None,
    after: bytes | None,
) -> list[PromptImage]:
    pieces: list[tuple[str, bytes]] = []
    for frame in frames:
        pieces.append(("keyframe", frame.jpeg))
    for frame in frames:
        if frame.fire_box is None:
            continue
        pieces.append(("crop", enlarge_crop(frame.jpeg, frame.fire_box)))
    if before is not None:
        pieces.append(("before", before))
    if after is not None:
        pieces.append(("after", after))
    images = []
    for index, (role, blob) in enumerate(pieces, start=1):
        if role not in ROLE_ORDER:
            raise ValueError(f"unknown image role {role}")
        encoded = base64.b64encode(blob).decode("ascii")
        images.append(
            PromptImage(
                index=index,
                role=role,
                data_url=f"data:image/jpeg;base64,{encoded}",
            )
        )
    return images


class QwenAnalyzer:
    def __init__(self, config: AppConfig) -> None:
        self._reasoner = QwenVisionReasoner(
            api_key=config.llm.api_key or None,
            base_url=config.llm.base_url,
            model=config.llm.model,
        )
        self.model = config.llm.model

    def analyze(
        self,
        alert_id: int,
        frames: list,
        before: bytes | None,
        after: bytes | None,
    ) -> dict:
        call = self._reasoner.analyze(
            incident_id=alert_id,
            images=prompt_images(frames, before, after),
        )
        return call.model_dump(by_alias=False)


def disabled_call(model: str) -> dict:
    return {
        "status": "FAILED",
        "provider": "dashscope",
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "evidence": None,
        "error_code": "VLM_DISABLED",
    }
