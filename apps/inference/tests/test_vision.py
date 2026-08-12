from fire_monitoring_inference.vision.qwen import QwenVisionReasoner


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": """{"schemaVersion":"1.0","hasVisibleFire":true,
                        "hasVisibleSmoke":false,"sourceNature":"open_flame",
                        "sceneType":"classroom","burningObjects":["paper"],
                        "peopleAtRisk":false,"riskLevel":"HIGH",
                        "reasoningSummary":"Visible flame near paper.",
                        "recommendedActions":["Verify the scene"],"confidence":0.86,
                        "uncertainties":[]}"""
                    }
                }
            ]
        }


class FakeClient:
    def __init__(self) -> None:
        self.request: dict | None = None

    def post(self, url: str, *, headers: dict, json: dict) -> FakeResponse:
        self.request = {"url": url, "headers": headers, "json": json}
        return FakeResponse()


def test_qwen_adapter_fails_safely_without_secret() -> None:
    reasoner = QwenVisionReasoner(api_key=None)
    result = reasoner.analyze(incident_id=1, image_data_urls=["data:image/jpeg;base64,AA=="])

    assert result.status == "FAILED"
    assert result.error_code == "VLM_NOT_CONFIGURED"
    assert result.reasoning_summary is None


def test_qwen_adapter_rejects_remote_urls_before_network_call() -> None:
    reasoner = QwenVisionReasoner(api_key="local-test-key")
    result = reasoner.analyze(incident_id=1, image_data_urls=["https://example.invalid/frame.jpg"])

    assert result.status == "FAILED"
    assert result.error_code == "VLM_UNSAFE_IMAGE_URL"


def test_qwen_adapter_uses_non_thinking_json_object_with_local_validation() -> None:
    client = FakeClient()
    reasoner = QwenVisionReasoner(api_key="local-test-key", model="qwen3.7-plus", client=client)

    result = reasoner.analyze(incident_id=None, image_data_urls=["data:image/jpeg;base64,AA=="])

    assert result.status == "SUCCEEDED"
    assert result.incident_id is None
    assert result.model == "qwen3.7-plus"
    assert client.request is not None
    assert client.request["json"]["enable_thinking"] is False
    assert client.request["json"]["response_format"] == {"type": "json_object"}
