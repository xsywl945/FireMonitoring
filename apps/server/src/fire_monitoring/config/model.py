from __future__ import annotations

from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ServerSettings(_Strict):
    host: str
    port: int = Field(ge=1, le=65535)
    cors_origins: list[str]


class DatabaseSettings(_Strict):
    host: str
    port: int = Field(ge=1, le=65535)
    name: str
    user: str
    password: str


class MinioSettings(_Strict):
    endpoint: str
    access_key: str
    secret_key: str
    bucket: str
    secure: bool


class MediaSettings(_Strict):
    rtsp_base: str
    whep_base: str
    rtsp_address: str
    hls_address: str
    webrtc_address: str
    webrtc_udp_address: str
    api_address: str
    playback_address: str
    config_path: str
    ffmpeg_path: str
    mediamtx_path: str


class LlmSettings(_Strict):
    enabled: bool
    base_url: str
    model: str
    api_key: str


class SmsSettings(_Strict):
    enabled: bool
    access_key_id: str
    access_key_secret: str
    sign_name: str
    template_code: str
    recipients: list[str]
    cooldown_seconds: int = Field(ge=0)


class Thresholds(_Strict):
    fire: float = Field(ge=0, le=1)
    smoke: float = Field(ge=0, le=1)


class ModelSettings(_Strict):
    path: str
    version: str
    imgsz: int = Field(ge=32, le=4096)
    device: str
    thresholds: Thresholds


class TemporalSettings(_Strict):
    n: int = Field(ge=1)
    m: int = Field(ge=1)
    candidate_n: int = Field(ge=1)
    clear_frames: int = Field(ge=1)
    cooldown_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if not self.candidate_n <= self.n <= self.m:
            raise ValueError("temporal thresholds must satisfy candidate_n <= n <= m")
        return self


class LocalizationSettings(_Strict):
    landmark_sigma_px: float = Field(gt=0)
    window_ms: int = Field(ge=0)


class PumpSettings(_Strict):
    enabled: bool
    serial_port: str
    zone_id: int | None = Field(default=None, gt=0)
    duration_ms: int = Field(ge=100, le=30_000)
    cooldown_seconds: int = Field(ge=0, le=3600)
    min_confidence: float = Field(ge=0, le=1)
    max_evidence_age_seconds: int = Field(ge=1, le=60)
    require_vlm: bool
    local_min_confidence: float = Field(ge=0, le=1)
    local_min_frames: int = Field(ge=1, le=100)
    journal_path: str

    @model_validator(mode="after")
    def ready(self) -> Self:
        if self.enabled and (not self.serial_port.strip() or self.zone_id is None):
            raise ValueError("pump.enabled requires serial_port and zone_id")
        return self


class AuthUser(_Strict):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1)
    display_name: str = Field(min_length=1, max_length=100)
    role: Literal["admin", "operator"]


class AuthSettings(_Strict):
    jwt_secret: str = Field(min_length=16)
    jwt_expiration_seconds: int = Field(ge=60)
    users: list[AuthUser] = Field(min_length=1)


class CameraDefaults(_Strict):
    default_fps: float = Field(gt=0, le=60)


class AppConfig(_Strict):
    server: ServerSettings
    database: DatabaseSettings
    minio: MinioSettings
    mediamtx: MediaSettings
    llm: LlmSettings
    sms: SmsSettings
    model: ModelSettings
    temporal: TemporalSettings
    localization: LocalizationSettings
    pump: PumpSettings
    auth: AuthSettings
    cameras: CameraDefaults
    timezone: str


def load_config(path: Path | None = None) -> AppConfig:
    file = path or Path("config.json")
    return AppConfig.model_validate_json(file.read_text(encoding="utf-8"))


def mask_secret(value: str) -> str:
    if value == "":
        return ""
    if len(value) <= 4:
        return "****"
    return f"{value[:2]}****{value[-2:]}"


def masked_config(config: AppConfig) -> dict:
    data = config.model_dump()
    data["database"]["password"] = mask_secret(data["database"]["password"])
    data["minio"]["access_key"] = mask_secret(data["minio"]["access_key"])
    data["minio"]["secret_key"] = mask_secret(data["minio"]["secret_key"])
    data["llm"]["api_key"] = mask_secret(data["llm"]["api_key"])
    data["sms"]["access_key_id"] = mask_secret(data["sms"]["access_key_id"])
    data["sms"]["access_key_secret"] = mask_secret(data["sms"]["access_key_secret"])
    data["auth"]["jwt_secret"] = mask_secret(data["auth"]["jwt_secret"])
    for user in data["auth"]["users"]:
        user["password"] = mask_secret(user["password"])
    return data
