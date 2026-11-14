from __future__ import annotations

import json
import time
from typing import Annotated, Any, Literal

import httpx
from pydantic import Field, ValidationError

from ..contracts import StrictModel

PROMPT_VERSION = "fire-evidence-v4"
ROLE_LABEL = {
    "keyframe": "关键帧",
    "crop": "火焰框放大",
    "before": "事件前",
    "after": "事件后",
}


class BurningObject(StrictModel):
    frame_index: int = Field(alias="frameIndex", ge=1, le=12)
    name: str = Field(min_length=1, max_length=40)
    evidence: str = Field(min_length=1, max_length=200)


class VlmEvidence(StrictModel):
    schema_version: Literal["4.0"] = Field(alias="schemaVersion")
    burning_objects: list[BurningObject] = Field(alias="burningObjects", max_length=10)
    suspected_cause: Literal[
        "electrical_short",
        "open_flame",
        "lab_reagent",
        "cooking_oil",
        "smoking",
        "unknown",
    ] = Field(alias="suspectedCause")
    energized_equipment: bool = Field(alias="energizedEquipment")
    liquid: bool
    oil_pan: bool = Field(alias="oilPan")
    metal_powder: bool = Field(alias="metalPowder")
    person_count: int = Field(alias="personCount", ge=0, le=50)
    person_location: str = Field(alias="personLocation", max_length=200)
    scene_type: Literal[
        "classroom",
        "laboratory",
        "electrical_room",
        "dormitory",
        "kitchen",
        "warehouse",
        "corridor",
    ] = Field(alias="sceneType")
    smoke_color: Literal["none", "white", "gray", "black", "unknown"] = Field(alias="smokeColor")
    smoke_density: Literal["none", "light", "dense", "unknown"] = Field(alias="smokeDensity")
    uncertainties: list[Annotated[str, Field(max_length=200)]] = Field(max_length=10)


class PromptImage(StrictModel):
    index: int = Field(ge=1, le=12)
    role: Literal["keyframe", "crop", "before", "after"]
    data_url: str


class VlmCall(StrictModel):
    status: Literal["SUCCEEDED", "FAILED"]
    provider: str
    model: str
    prompt_version: str = Field(alias="promptVersion")
    evidence: dict | None = None
    error_code: str | None = Field(default=None, alias="errorCode")
    latency_ms: float | None = Field(default=None, alias="latencyMs", ge=0)


VLM_RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "fire_evidence_v4",
        "strict": True,
        "schema": VlmEvidence.model_json_schema(by_alias=True),
    },
}


SYSTEM_PROMPT = """你是校园火情监测的视觉证据记录员。只根据给出的画面描述看得见的事实。
不判断火灾类别，不选择灭火剂，不决定是否喷水、断电或疏散。
屏幕、手机、海报、反光和印刷品里的火焰或烟雾不算现场实火。
把烟和蒸汽、雾、灰尘、眩光、灯光、红色或橙色物体区分开。
证据不足时把疑似原因设为 unknown，燃烧物留空。
烟的颜色和浓度设为 unknown 或 none，并写入 uncertainties。
自由文本用简体中文。枚举值保持英文，不要改写。
只返回一个符合给定结构的 JSON 对象。"""


def _user_prompt(images: list[PromptImage]) -> str:
    lines = [
        "下面按画面编号给出关键帧、火焰框放大图，以及事件前后的画面。",
        "燃烧物的 frameIndex 必须引用这些编号。",
        "返回字段：schemaVersion=4.0，burningObjects（frameIndex、name、evidence），",
        "suspectedCause（electrical_short|open_flame|lab_reagent|cooking_oil|smoking|unknown），",
        "energizedEquipment，liquid，oilPan，metalPowder，personCount，personLocation，",
        "sceneType（classroom|laboratory|electrical_room|dormitory|kitchen|warehouse|corridor），",
        "smokeColor（none|white|gray|black|unknown），smokeDensity（none|light|dense|unknown），uncertainties。",
    ]
    lines.extend(
        f"画面{image.index}：{ROLE_LABEL[image.role]}。" for image in images
    )
    return "\n".join(lines)


class QwenVisionReasoner:
    provider = "dashscope"

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        model: str = "qwen3.7-plus",
        client: httpx.Client | Any | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = client or httpx.Client(timeout=httpx.Timeout(25.0, connect=3.0))

    def analyze(self, *, incident_id: int | None, images: list[PromptImage]) -> VlmCall:
        started = time.perf_counter()
        if not self.api_key:
            return self._failure(incident_id, "VLM_NOT_CONFIGURED", started)
        if not images or len(images) > 12:
            return self._failure(incident_id, "VLM_INVALID_IMAGE_COUNT", started)
        if any(not image.data_url.startswith("data:image/") for image in images):
            return self._failure(incident_id, "VLM_UNSAFE_IMAGE_URL", started)
        content: list[dict[str, Any]] = [{"type": "text", "text": _user_prompt(images)}]
        for image in images:
            content.append(
                {"type": "text", "text": f"画面{image.index}，{ROLE_LABEL[image.role]}。"}
            )
            content.append({"type": "image_url", "image_url": {"url": image.data_url}})
        request = {
            "model": self.model,
            "temperature": 0,
            "enable_thinking": False,
            "response_format": VLM_RESPONSE_FORMAT,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
        }
        try:
            response = self._client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=request,
            )
            response.raise_for_status()
            raw = response.json()["choices"][0]["message"]["content"]
            evidence = VlmEvidence.model_validate(json.loads(raw))
        except (httpx.TimeoutException, TimeoutError):
            return self._failure(incident_id, "VLM_TIMEOUT", started)
        except (ValidationError, ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError):
            return self._failure(incident_id, "VLM_INVALID_RESPONSE", started)
        except (httpx.HTTPError, OSError):
            return self._failure(incident_id, "VLM_API_ERROR", started)
        return VlmCall(
            status="SUCCEEDED",
            provider=self.provider,
            model=self.model,
            promptVersion=PROMPT_VERSION,
            evidence=evidence.model_dump(by_alias=False),
            latencyMs=self._latency_ms(started),
        )

    def _failure(self, incident_id: int | None, error_code: str, started: float) -> VlmCall:
        del incident_id
        return VlmCall(
            status="FAILED",
            provider=self.provider,
            model=self.model,
            promptVersion=PROMPT_VERSION,
            errorCode=error_code,
            latencyMs=self._latency_ms(started),
        )

    @staticmethod
    def _latency_ms(started: float) -> float:
        return max(0, (time.perf_counter() - started) * 1000)
