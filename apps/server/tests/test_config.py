import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from fire_monitoring.config import apply_public_update, load_config, public_config

EXAMPLE = Path(__file__).resolve().parents[3] / "config.example.json"


def test_example_config_loads_model_and_thresholds() -> None:
    config = load_config(EXAMPLE)
    assert config.model.path == "models/yolo26s-ft-2026-11-04/best.pt"
    assert config.model.thresholds.fire == 0.3
    assert config.model.thresholds.smoke == 0.35
    assert config.server.port == 8080
    assert config.sms.recipients == []
    assert config.llm.base_url.startswith("https://dashscope.aliyuncs.com")
    assert config.pump.serial_port == ""


def test_config_rejects_unknown_field(tmp_path: Path) -> None:
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["redis"] = {"url": "redis://127.0.0.1:6379/0"}
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(path)


def test_enabled_pump_requires_port_and_room(tmp_path: Path) -> None:
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["pump"]["enabled"] = True
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(path)


def test_public_config_omits_secrets() -> None:
    config = load_config(EXAMPLE)
    public = public_config(config)
    text = json.dumps(public)
    assert config.auth.jwt_secret not in text
    assert config.database.password not in text
    assert "password" not in public["database"]
    assert "users" not in public["auth"]
    assert "jwt_secret" not in public["auth"]
    assert "api_key" not in public["llm"]
    assert public["model"]["thresholds"]["fire"] == 0.3
    assert public["health"]["freeze_seconds"] == 5


def test_public_update_keeps_secrets() -> None:
    current = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    merged = apply_public_update(current, {"cameras": {"default_fps": 8}})
    assert merged["cameras"]["default_fps"] == 8
    assert merged["database"]["password"] == current["database"]["password"]
    assert merged["auth"]["users"][0]["password"] == "123456"
    assert merged["auth"]["jwt_secret"] == current["auth"]["jwt_secret"]
    with pytest.raises(ValueError):
        apply_public_update(current, {"database": {"password": "nope"}})
    with pytest.raises(ValueError):
        apply_public_update(current, {"auth": {"users": []}})
