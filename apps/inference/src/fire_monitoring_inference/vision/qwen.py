from __future__ import annotations

import json
import re
import time
from typing import Annotated, Any, Literal

import httpx
from pydantic import Field, ValidationError

from ..contracts import StrictModel, VlmAnalysisPayload

PROMPT_VERSION = "fire-risk-v3"


class VlmJudgement(StrictModel):
    schema_version: Literal["1.0"] = Field(alias="schemaVersion")
    has_visible_fire: bool = Field(alias="hasVisibleFire")
    has_visible_smoke: bool = Field(alias="hasVisibleSmoke")
    source_nature: Literal["electrical", "open_flame", "chemical", "cooking", "unknown"] = Field(
        alias="sourceNature"
    )
    scene_type: Literal["classroom", "laboratory", "corridor", "other"] = Field(alias="sceneType")
    burning_objects: list[Annotated[str, Field(max_length=100)]] = Field(
        alias="burningObjects", max_length=10
    )
    people_at_risk: bool = Field(alias="peopleAtRisk")
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = Field(alias="riskLevel")
    reasoning_summary: str = Field(alias="reasoningSummary", max_length=1000)
    recommended_actions: list[Annotated[str, Field(max_length=100)]] = Field(
        alias="recommendedActions", max_length=10
    )
    confidence: float = Field(ge=0, le=1)
    uncertainties: list[Annotated[str, Field(max_length=200)]] = Field(max_length=10)


VLM_RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "fire_risk_judgement",
        "strict": True,
        "schema": VlmJudgement.model_json_schema(by_alias=True),
    },
}


SYSTEM_PROMPT = """You are the visual verification gate for a classroom and laboratory fire
monitoring research prototype. Analyze only the supplied chronological camera frames. Treat fire
or smoke shown on a monitor, phone, poster, reflection, or printed image as NOT physically present.
Distinguish smoke from steam, fog, dust, glare, sunlight, lamps and bright red/orange objects. Set
hasVisibleFire or hasVisibleSmoke true only for a real physical phenomenon visible in the monitored
scene. Never claim that emergency services were contacted, power was cut, or an evacuation
happened. Return exactly one JSON object matching the requested schema. When evidence is
insufficient, set both visibility fields false, use sourceNature=unknown, lower confidence, and
explain uncertainty. Write reasoningSummary, burningObjects, recommendedActions and uncertainties
in concise Simplified Chinese. Keep the summary within two short sentences, recommendations to at
most three concrete actions, and avoid boilerplate or repeated caveats.
Keep enum values unchanged."""

USER_PROMPT = """Assess these chronological classroom/laboratory camera evidence frames jointly.
Use temporal consistency across frames to reject screen content, reflections and transient
artifacts. Return JSON fields:
schemaVersion='1.0', hasVisibleFire, hasVisibleSmoke, sourceNature
(electrical|open_flame|chemical|cooking|unknown), sceneType
(classroom|laboratory|corridor|other), burningObjects, peopleAtRisk, riskLevel
(LOW|MEDIUM|HIGH|CRITICAL), reasoningSummary, recommendedActions, confidence, uncertainties."""


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

    def analyze(self, *, incident_id: int | None, image_data_urls: list[str]) -> VlmAnalysisPayload:
        started = time.perf_counter()
        if not self.api_key:
            return self._failure(incident_id, "VLM_NOT_CONFIGURED", started)
        if not image_data_urls or len(image_data_urls) > 3:
            return self._failure(incident_id, "VLM_INVALID_IMAGE_COUNT", started)
        if any(not url.startswith("data:image/") for url in image_data_urls):
            return self._failure(incident_id, "VLM_UNSAFE_IMAGE_URL", started)

        content: list[dict[str, Any]] = [{"type": "text", "text": USER_PROMPT}]
        for index, url in enumerate(image_data_urls, start=1):
            content.append({"type": "text", "text": f"Chronological evidence frame {index}."})
            content.append({"type": "image_url", "image_url": {"url": url}})
        request = {
            "model": self.model,
            "temperature": 0,
            "enable_thinking": False,
            # JSON Object mode only guarantees syntactically valid JSON. Qwen3.7-Plus
            # supports strict JSON Schema output, which prevents fields such as
            # uncertainties from changing between an array and a string. Pydantic
            # remains the independent local fail-closed validation boundary.
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
            judgement = VlmJudgement.model_validate(self._parse_json(raw))
        except (httpx.TimeoutException, TimeoutError):
            return self._failure(incident_id, "VLM_TIMEOUT", started)
        except (ValidationError, ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError):
            return self._failure(incident_id, "VLM_INVALID_RESPONSE", started)
        except (httpx.HTTPError, OSError):
            return self._failure(incident_id, "VLM_API_ERROR", started)

        return VlmAnalysisPayload(
            incidentId=incident_id,
            status="SUCCEEDED",
            provider=self.provider,
            model=self.model,
            promptVersion=PROMPT_VERSION,
            hasVisibleFire=judgement.has_visible_fire,
            hasVisibleSmoke=judgement.has_visible_smoke,
            sourceNature=judgement.source_nature,
            sceneType=judgement.scene_type,
            riskLevel=judgement.risk_level,
            reasoningSummary=judgement.reasoning_summary,
            recommendedActions=judgement.recommended_actions,
            confidence=judgement.confidence,
            uncertainties=judgement.uncertainties,
            latencyMs=self._latency_ms(started),
        )

    @staticmethod
    def _parse_json(raw: Any) -> dict[str, Any]:
        if not isinstance(raw, str):
            raise ValueError("model content is not text")
        stripped = raw.strip()
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL)
        if fenced:
            stripped = fenced.group(1)
        value = json.loads(stripped)
        if not isinstance(value, dict):
            raise ValueError("model content is not an object")
        return value

    def _failure(
        self, incident_id: int | None, error_code: str, started: float
    ) -> VlmAnalysisPayload:
        return VlmAnalysisPayload(
            incidentId=incident_id,
            status="FAILED",
            provider=self.provider,
            model=self.model,
            promptVersion=PROMPT_VERSION,
            recommendedActions=[],
            uncertainties=["cloud_semantic_analysis_unavailable"],
            errorCode=error_code,
            latencyMs=self._latency_ms(started),
        )

    @staticmethod
    def _latency_ms(started: float) -> float:
        return max(0, (time.perf_counter() - started) * 1000)
