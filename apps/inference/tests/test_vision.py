from fire_monitoring_inference.vision.qwen import QwenVisionReasoner


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
