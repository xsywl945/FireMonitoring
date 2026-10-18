from fire_monitoring_inference.config import ServiceConfig


def test_disabled_cloud_overrides_old_gate_flag_and_retains_key(monkeypatch):
    monkeypatch.setenv("INFERENCE_VLM_ENABLED", "false")
    monkeypatch.setenv("INFERENCE_VLM_GATE_ENABLED", "true")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key-not-a-real-secret")
    config = ServiceConfig.from_env()
    assert config.vlm_gate_active is False
    assert config.pump.require_vlm is False
    assert config.public_dict()["vlm_enabled"] is False
    assert config.public_dict()["vlm_gate_enabled"] is False
    assert config.public_dict()["dashscope_configured"] is True
    monkeypatch.setenv("INFERENCE_VLM_ENABLED", "true")
    config = ServiceConfig.from_env()
    assert config.vlm_gate_active is True
    assert config.pump.require_vlm is True
