import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
from fire_monitoring_inference.contracts import utc_now
from fire_monitoring_inference.pump import PumpConfig, PumpController

from fire_monitoring.alerts.pipeline import AlertPipeline, ConfirmedJob
from fire_monitoring.config import load_config
from fire_monitoring.db import make_engine, make_session_factory
from fire_monitoring.detection.ingest import FrameShot
from fire_monitoring.events.hub import EventHub
from fire_monitoring.evidence.store import MemoryStore
from fire_monitoring.localization.observe import source_from_box
from fire_monitoring.models import Alert, AlertFrame, Room, SmsDispatch
from fire_monitoring.sms.aliyun import AliyunSmsSender
from fire_monitoring.sms.service import SmsService
from fire_monitoring.config.model import SmsSettings

EXAMPLE = Path(__file__).resolve().parents[3] / "config.example.json"


class FakeAnalyzer:
    def __init__(self) -> None:
        self.calls = []

    def analyze(self, alert_id: int, jpegs: list[bytes]) -> dict:
        self.calls.append((alert_id, list(jpegs)))
        return {
            "status": "SUCCEEDED",
            "provider": "fake",
            "model": "fake",
            "prompt_version": "test",
            "has_visible_fire": True,
            "has_visible_smoke": False,
            "source_nature": "open_flame",
            "scene_type": "classroom",
            "risk_level": "HIGH",
            "reasoning_summary": "画面中有明火",
            "recommended_actions": ["疏散"],
            "burning_objects": ["纸"],
            "people_at_risk": True,
            "confidence": 0.9,
            "uncertainties": [],
            "error_code": None,
        }


class FakeSms:
    def __init__(self) -> None:
        self.sent = []

    def send(self, phone: str, template_param: dict[str, str]) -> None:
        self.sent.append((phone, template_param))


class FakeTransport:
    def __init__(self) -> None:
        self.commands = []

    def prepare(self) -> None:
        return None

    def request(self, command: str) -> str:
        self.commands.append(command)
        if command.startswith("RUN "):
            trace = command.split()[1]
            return f"ACK {trace} ON"
        if command == "STATUS":
            return "STATE OFF NONE"
        return "STOPPED"

    def close(self) -> None:
        return None


def _config():
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["llm"]["enabled"] = True
    data["sms"]["enabled"] = True
    data["sms"]["recipients"] = ["13800000000"]
    data["sms"]["cooldown_seconds"] = 300
    return load_config_from(data)


def load_config_from(data: dict):
    from fire_monitoring.config import AppConfig

    return AppConfig.model_validate(data)


def _factory(tmp_path: Path):
    from fire_monitoring.db import Base
    import fire_monitoring.models  # noqa: F401

    engine = make_engine(f"sqlite:///{tmp_path / 'alerts.db'}")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def _submit(pipeline: AlertPipeline, **kwargs) -> None:
    pipeline.submit(
        ConfirmedJob(confirmed_monotonic=time.perf_counter(), **kwargs)
    )
    pipeline.wait()


def _calibration() -> dict:
    return {
        "intrinsics": [[800, 0, 320], [0, 800, 240], [0, 0, 1]],
        "distortion": [0, 0, 0, 0, 0],
        "landmarks": [
            {"world_m": [0, 0, 0], "pixel": [1, 1]},
            {"world_m": [1, 0, 0], "pixel": [2, 1]},
            {"world_m": [1, 1, 0], "pixel": [2, 2]},
            {"world_m": [0, 1, 0], "pixel": [1, 2]},
        ],
    }


def _calibrations() -> dict:
    return {camera_id: _calibration() for camera_id in (1, 2, 3, 4)}


def test_confirm_alert_saves_position_frames_analysis_sms_and_pump(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    session = factory()
    session.add(Room(name="101", scene_type="classroom", created_at=utc_now()))
    session.commit()
    room = session.query(Room).one()
    now = utc_now()
    sources = [
        source_from_box(
            camera_id=camera_id,
            class_name="fire",
            bbox_xyxy=(10, 10, 40, 50),
            confidence=0.8,
            image_width=100,
            image_height=80,
            captured_at=now,
        )
        for camera_id in (1, 2)
    ]
    frames = [
        FrameShot(camera_id=camera_id, jpeg=f"frame-{camera_id}".encode(), captured_at=now, width=100, height=80)
        for camera_id in (1, 2, 3, 4)
    ]
    evidence = MemoryStore()
    analyzer = FakeAnalyzer()
    sender = FakeSms()
    sms = SmsService(_config(), sender)
    transport = FakeTransport()
    pump = PumpController(
        config=PumpConfig(
            enabled=True,
            port="COM3",
            zone_id=room.id,
            duration_ms=5000,
            cooldown_seconds=0,
            require_vlm=False,
            local_min_confidence=0.3,
            local_min_frames=1,
        ),
        journal_path=tmp_path / "pump.sqlite3",
        transport=transport,
    )

    seen = {}

    def localizer(manifest):
        from fire_monitoring_inference.localization import LocalizationInput

        request = LocalizationInput.model_validate_json(manifest.read_bytes())
        seen["cameras"] = set(request.views)
        seen["pixel"] = request.views[1].source.pixel
        return {
            "status": "ESTIMATED",
            "xyz": [1.5, 2.5, 0.2],
            "covariance": [[0.1, 0, 0], [0, 0.1, 0], [0, 0, 0.1]],
            "condition_number": 8.0,
            "support_camera_ids": [1, 2],
        }

    config = _config()
    pipeline = AlertPipeline(
        config,
        factory,
        evidence,
        analyzer,
        sms,
        pump,
        EventHub(),
        localizer=localizer,
        on_fatal=lambda: None,
    )
    pipeline.start()
    observations = [
        {
            "camera_id": 1,
            "class_name": "fire",
            "score": 0.8,
            "effective_frames": 3,
            "duration_ms": 400,
        }
    ]
    _submit(
        pipeline,
        room_id=room.id,
        alert_type="FIRE",
        started_at=now,
        sources=sources,
        calibrations=_calibrations(),
        frames=frames,
        pump_observations=observations,
    )
    stored = session.query(Alert).one()
    position = json.loads(stored.position_json)
    assert seen["cameras"] == {1, 2, 3, 4}
    assert seen["pixel"] == sources[0].pixel
    assert position["status"] == "ESTIMATED"
    assert position["xyz"] == [1.5, 2.5, 0.2]
    assert position["condition_number"] == 8.0
    assert position["support_camera_ids"] == [1, 2]
    assert session.query(AlertFrame).count() == 4
    assert len(evidence.objects) == 4
    analysis = json.loads(stored.analysis_json)
    assert analysis["reasoning_summary"] == "画面中有明火"
    assert analysis["burning_objects"] == ["纸"]
    assert analysis["people_at_risk"] is True
    assert analyzer.calls[0][1] == [frame.jpeg for frame in frames]
    expected_time = now.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")
    assert sender.sent == [("13800000000", {"room": "101", "type": "火焰", "time": expected_time})]
    assert transport.commands[0].startswith("RUN ")

    later = now + timedelta(seconds=10)
    _submit(
        pipeline,
        room_id=room.id,
        alert_type="FIRE",
        started_at=later,
        sources=sources,
        calibrations=_calibrations(),
        frames=frames,
        pump_observations=[],
    )
    assert len(sender.sent) == 1
    assert session.query(SmsDispatch).count() == 1
    pipeline.stop()
    pump.close()


def test_disabled_sms_and_llm_are_not_called(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    session = factory()
    session.add(Room(name="102", scene_type="laboratory", created_at=utc_now()))
    session.commit()
    room = session.query(Room).one()
    config = load_config(EXAMPLE)
    analyzer = FakeAnalyzer()
    sender = FakeSms()
    now = datetime.now(UTC)
    frames = [
        FrameShot(camera_id=camera_id, jpeg=b"jpg", captured_at=now, width=100, height=80)
        for camera_id in (1, 2, 3, 4)
    ]
    called = []
    pipeline = AlertPipeline(
        config,
        factory,
        MemoryStore(),
        analyzer,
        SmsService(config, sender),
        None,
        EventHub(),
        localizer=lambda _manifest: called.append(True),
        on_fatal=lambda: None,
    )
    pipeline.start()
    _submit(
        pipeline,
        room_id=room.id,
        alert_type="SMOKE",
        started_at=now,
        sources=[],
        calibrations=_calibrations(),
        frames=frames,
        pump_observations=[],
    )
    pipeline.stop()
    assert called == []
    assert analyzer.calls == []
    assert sender.sent == []
    position = json.loads(session.query(Alert).one().position_json)
    assert position == {"status": "UNOBSERVABLE", "support_camera_ids": []}
    assert "xyz" not in position


def test_aliyun_sender_posts_template_and_raises_on_failure() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"Code": "OK", "Message": "OK"})

    settings = SmsSettings(
        enabled=True,
        access_key_id="key",
        access_key_secret="secret",
        sign_name="签名",
        template_code="SMS_1",
        recipients=["13800000000"],
        cooldown_seconds=60,
    )
    sender = AliyunSmsSender(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
    sender.send("13800000000", {"room": "101", "type": "火焰", "time": "2026-11-10 08:00:00"})
    assert "Action=SendSms" in seen["body"]
    assert "PhoneNumbers=13800000000" in seen["body"]
    assert "TemplateCode=SMS_1" in seen["body"]

    def failed(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"Code": "isv.BUSINESS_LIMIT_CONTROL", "Message": "限流"})

    sender = AliyunSmsSender(settings, client=httpx.Client(transport=httpx.MockTransport(failed)))
    with pytest.raises(RuntimeError, match="限流"):
        sender.send("13800000000", {"room": "101", "type": "火焰", "time": "2026-11-10 08:00:00"})
