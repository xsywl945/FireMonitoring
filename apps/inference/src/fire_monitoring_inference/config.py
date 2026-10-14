from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


def _env(name: str, default: Any) -> Any:
    value = os.getenv(name)
    return default if value is None or value == "" else value


class ServiceConfig(BaseModel):
    """Environment-backed process configuration with no secret serialization."""

    model_config = ConfigDict(extra="forbid")

    host: str = "127.0.0.1"
    port: int = Field(default=8091, ge=1, le=65535)
    control_token: SecretStr = SecretStr("local-camera-control")
    source: str = Field(default="inference-worker-1", min_length=1, max_length=100)
    model_version: str = Field(default="mock-fire-yolo-0.1.0", max_length=100)
    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_stream: str = "monitoring.events"
    temporal_n: int = Field(default=3, ge=1, le=100)
    temporal_m: int = Field(default=5, ge=1, le=100)
    candidate_n: int = Field(default=1, ge=1, le=100)
    min_confidence: float = Field(default=0.45, ge=0, le=1)
    clear_frames: int = Field(default=3, ge=1, le=100)
    cooldown_ms: int = Field(default=10_000, ge=0)
    fusion_window_ms: int = Field(default=500, ge=0, le=10_000)
    dashscope_api_key: SecretStr | None = None
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_model: str = "qwen3.7-plus"
    vlm_gate_enabled: bool = False
    vlm_gate_min_confidence: float = Field(default=0.7, ge=0, le=1)
    vlm_gate_fail_open: bool = False
    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: SecretStr | None = None
    minio_secret_key: SecretStr | None = None
    minio_bucket: str = "fire-evidence"
    minio_secure: bool = False

    @model_validator(mode="after")
    def validate_temporal_thresholds(self) -> ServiceConfig:
        if not self.candidate_n <= self.temporal_n <= self.temporal_m:
            raise ValueError(
                "temporal thresholds must satisfy candidate_n <= temporal_n <= temporal_m"
            )
        return self

    @classmethod
    def from_env(cls) -> ServiceConfig:
        key = os.getenv("DASHSCOPE_API_KEY")
        minio_access_key = os.getenv("MINIO_ROOT_USER")
        minio_secret_key = os.getenv("MINIO_ROOT_PASSWORD")
        return cls(
            control_token=SecretStr(_env("INFERENCE_CONTROL_TOKEN", "local-camera-control")),
            host=_env("INFERENCE_HOST", "127.0.0.1"),
            port=_env("INFERENCE_PORT", 8091),
            source=_env("INFERENCE_SOURCE", "inference-worker-1"),
            model_version=_env("INFERENCE_MODEL_VERSION", "mock-fire-yolo-0.1.0"),
            redis_url=_env("INFERENCE_REDIS_URL", "redis://127.0.0.1:6379/0"),
            redis_stream=_env("INFERENCE_REDIS_STREAM", "monitoring.events"),
            temporal_n=_env("INFERENCE_TEMPORAL_N", 3),
            temporal_m=_env("INFERENCE_TEMPORAL_M", 5),
            candidate_n=_env("INFERENCE_CANDIDATE_N", 1),
            min_confidence=_env("INFERENCE_MIN_CONFIDENCE", 0.45),
            clear_frames=_env("INFERENCE_CLEAR_FRAMES", 3),
            cooldown_ms=_env("INFERENCE_COOLDOWN_MS", 10_000),
            fusion_window_ms=_env("INFERENCE_FUSION_WINDOW_MS", 500),
            dashscope_api_key=SecretStr(key) if key else None,
            dashscope_base_url=_env(
                "DASHSCOPE_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
            dashscope_model=_env("DASHSCOPE_MODEL", "qwen3.7-plus"),
            vlm_gate_enabled=_env("INFERENCE_VLM_GATE_ENABLED", False),
            vlm_gate_min_confidence=_env("INFERENCE_VLM_GATE_MIN_CONFIDENCE", 0.7),
            vlm_gate_fail_open=_env("INFERENCE_VLM_GATE_FAIL_OPEN", False),
            minio_endpoint=_env("INFERENCE_MINIO_ENDPOINT", "127.0.0.1:9000"),
            minio_access_key=SecretStr(minio_access_key) if minio_access_key else None,
            minio_secret_key=SecretStr(minio_secret_key) if minio_secret_key else None,
            minio_bucket=_env("MINIO_BUCKET", "fire-evidence"),
            minio_secure=_env("INFERENCE_MINIO_SECURE", False),
        )

    def public_dict(self) -> dict[str, Any]:
        data = self.model_dump(
            exclude={
                "control_token",
                "dashscope_api_key",
                "redis_url",
                "minio_access_key",
                "minio_secret_key",
            }
        )
        data["redis_configured"] = bool(self.redis_url)
        data["dashscope_configured"] = self.dashscope_api_key is not None
        data["minio_configured"] = (
            self.minio_access_key is not None and self.minio_secret_key is not None
        )
        return data
