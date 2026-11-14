import json

import pytest
from pydantic import ValidationError

from fire_monitoring_inference.vision.qwen import PROMPT_VERSION, QwenVisionReasoner, VlmEvidence


def _evidence(**overrides) -> dict:
    body = {
        "schemaVersion": "4.0",
        "burningObjects": [{"frameIndex": 1, "name": "纸", "evidence": "画面1桌面起火"}],
        "suspectedCause": "open_flame",
        "energizedEquipment": False,
        "liquid": False,
        "oilPan": False,
        "metalPowder": False,
        "personCount": 0,
        "personLocation": "",
        "sceneType": "classroom",
        "smokeColor": "none",
        "smokeDensity": "none",
        "uncertainties": [],
    }
    body.update(overrides)
    return body


class FakeResponse:
    def __init__(self, content: str) -> None:
        self._content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"choices": [{"message": {"content": self._content}}]}


class FakeClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.request: dict | None = None

    def post(self, url: str, *, headers: dict, json: dict) -> FakeResponse:
        self.request = {"url": url, "headers": headers, "json": json}
        return FakeResponse(self.content)


def _image():
    from fire_monitoring_inference.vision.qwen import PromptImage

    return [PromptImage(index=1, role="keyframe", data_url="data:image/jpeg;base64,AA==")]


def test_qwen_adapter_fails_without_secret() -> None:
    reasoner = QwenVisionReasoner(api_key=None)
    result = reasoner.analyze(incident_id=1, images=_image())
    assert result.status == "FAILED"
    assert result.error_code == "VLM_NOT_CONFIGURED"
    assert result.evidence is None


def test_qwen_adapter_rejects_remote_urls_before_network_call() -> None:
    from fire_monitoring_inference.vision.qwen import PromptImage

    reasoner = QwenVisionReasoner(api_key="local-test-key")
    images = [PromptImage(index=1, role="before", data_url="https://example.invalid/frame.jpg")]
    result = reasoner.analyze(incident_id=1, images=images)
    assert result.status == "FAILED"
    assert result.error_code == "VLM_UNSAFE_IMAGE_URL"


def test_qwen_adapter_uses_fixed_response_and_v4_schema() -> None:
    client = FakeClient(json.dumps(_evidence(), ensure_ascii=False))
    reasoner = QwenVisionReasoner(api_key="local-test-key", model="qwen3.7-plus", client=client)
    result = reasoner.analyze(incident_id=None, images=_image())
    assert result.status == "SUCCEEDED"
    assert result.prompt_version == PROMPT_VERSION
    assert result.evidence["burning_objects"][0]["name"] == "纸"
    assert result.evidence["suspected_cause"] == "open_flame"
    assert result.model == "qwen3.7-plus"
    assert client.request is not None
    assert client.request["json"]["enable_thinking"] is False
    assert "灭火" not in client.request["json"]["messages"][0]["content"] or "不选择灭火剂" in (
        client.request["json"]["messages"][0]["content"]
    )
    response_format = client.request["json"]["response_format"]
    assert response_format["json_schema"]["name"] == "fire_evidence_v4"
    assert response_format["json_schema"]["strict"] is True
    schema = response_format["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["energizedEquipment"]["type"] == "boolean"
    assert set(schema["required"]) == set(schema["properties"])


def test_qwen_invalid_enum_fails_fast() -> None:
    client = FakeClient(json.dumps(_evidence(suspectedCause="chemical")))
    reasoner = QwenVisionReasoner(api_key="local-test-key", client=client)
    result = reasoner.analyze(incident_id=1, images=_image())
    assert result.status == "FAILED"
    assert result.error_code == "VLM_INVALID_RESPONSE"


def test_evidence_model_rejects_unknown_fields() -> None:
    body = _evidence()
    body["riskLevel"] = "HIGH"
    with pytest.raises(ValidationError):
        VlmEvidence.model_validate(body)
