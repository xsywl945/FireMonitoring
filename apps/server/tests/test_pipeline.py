import json
import logging
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient
from fire_monitoring_inference.contracts import Detection
from fire_monitoring_inference.pump import PumpConfig, PumpController

from fire_monitoring.alerts.pipeline import AlertPipeline, ConfirmedJob
from fire_monitoring.config import AppConfig, load_config
from fire_monitoring.db import Base, make_engine, make_session_factory
from fire_monitoring.detection.capture import CapturedFrame, FrameBuffer
from fire_monitoring.detection.ingest import FrameShot
from fire_monitoring.detection.worker import Assignment, due_cameras
from fire_monitoring.events.hub import EventHub
from fire_monitoring.evidence.store import MemoryStore
from fire_monitoring.main import create_app
from fire_monitoring.models import Alert, AlertEvent, Camera, Room, RoomCamera
from fire_monitoring.sms.service import SmsService

EXAMPLE = Path(__file__).resolve().parents[3] / "config.example.json"


class ScriptedDetector:
    def __init__(self) -> None:
        self.batches: list[int] = []
        self.model_version = "test"

    def detect(self, images):
        self.batches.append(len(images))
        if not images:
            raise RuntimeError("empty batch")
        hit = Detection(className="fire", confidence=0.92, bboxXyxy=(8, 8, 30, 30))
        return [[hit] for _image in images]


class ExplodingDetector:
    model_version = "test"

    def detect(self, images):
        raise RuntimeError("detector exploded")


class BlockingAnalyzer:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls: list[int] = []

    def analyze(self, alert_id: int, jpegs: list[bytes]) -> dict:
        self.calls.append(alert_id)
        self.started.set()
        if not self.release.wait(30):
            raise TimeoutError("qwen stayed blocked")
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
            "people_at_risk": False,
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


class FrameGate:
    def __init__(self, frame) -> None:
        self.frame = frame
        self.go = threading.Event()

    def open(self, _assignment):
        return _Reader(self)


class _Reader:
    def __init__(self, gate: FrameGate) -> None:
        self.gate = gate
        self.released = False

    def read(self):
        if self.released:
            return False, None
        if not self.gate.go.wait(0.05):
            return False, None
        return True, self.gate.frame

    def release(self) -> None:
        self.released = True


def _config() -> AppConfig:
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["llm"]["enabled"] = True
    data["sms"]["enabled"] = True
    data["sms"]["recipients"] = ["13800000000"]
    data["temporal"]["n"] = 2
    data["temporal"]["m"] = 3
    data["temporal"]["candidate_n"] = 1
    data["temporal"]["cooldown_ms"] = 0
    data["localization"]["window_ms"] = 2000
    return AppConfig.model_validate(data)


def _calibration() -> str:
    return json.dumps(
        {
            "intrinsics": [[800, 0, 32], [0, 800, 24], [0, 0, 1]],
            "distortion": [0, 0, 0, 0, 0],
            "landmarks": [
                {"world_m": [0, 0, 0], "pixel": [1, 1]},
                {"world_m": [1, 0, 0], "pixel": [2, 1]},
                {"world_m": [1, 1, 0], "pixel": [2, 2]},
                {"world_m": [0, 1, 0], "pixel": [1, 2]},
            ],
        }
    )


def test_ring_keeps_only_the_latest_frame_and_a_low_rate_sample() -> None:
    buffer = FrameBuffer(ring_fps=2, ring_seconds=15)
    frames = [
        CapturedFrame(image=None, jpeg=bytes([index]), captured_at=datetime.now(UTC), width=1, height=1)
        for index in range(3)
    ]
    buffer.push(frames[0], 0)
    buffer.push(frames[1], 0.1)
    buffer.push(frames[2], 0.6)
    assert buffer.snapshot() is frames[2]
    assert list(buffer.ring) == [frames[0], frames[2]]


def test_due_cameras_follow_target_fps() -> None:
    cameras = [
        Assignment(1, camera_id, f"cam{camera_id}", 10, None, [1, 2]) for camera_id in (1, 2)
    ]
    pending: dict[int, float] = {}
    assert [item.camera_id for item in due_cameras(cameras, 0, pending)] == [1, 2]
    pending[1] = 0.1
    pending[2] = 0.1
    assert due_cameras(cameras, 0.05, pending) == []
    assert [item.camera_id for item in due_cameras(cameras, 0.1, pending)] == [1, 2]


def test_require_vlm_holds_the_pump_until_analysis(tmp_path: Path) -> None:
    config = _config()
    config.pump.require_vlm = True
    engine = make_engine(f"sqlite:///{tmp_path / 'hold.db'}")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    session = factory()
    session.add(Room(name="201", scene_type="classroom", created_at=datetime.now(UTC)))
    session.commit()
    room = session.query(Room).one()
    analyzer = BlockingAnalyzer()
    sender = FakeSms()
    transport = FakeTransport()
    pump = PumpController(
        config=PumpConfig(
            enabled=True,
            port="COM3",
            zone_id=room.id,
            duration_ms=5000,
            cooldown_seconds=0,
            require_vlm=True,
            local_min_confidence=0.3,
            local_min_frames=1,
        ),
        journal_path=tmp_path / "pump.sqlite3",
        transport=transport,
    )
    pipeline = AlertPipeline(
        config,
        factory,
        MemoryStore(),
        analyzer,
        SmsService(config, sender),
        pump,
        EventHub(),
        localizer=lambda _manifest: {"status": "UNOBSERVABLE", "support_camera_ids": []},
        on_fatal=lambda: None,
    )
    pipeline.start()
    now = datetime.now(UTC)
    frames = [
        FrameShot(camera_id=1, jpeg=b"a", captured_at=now, width=8, height=8),
        FrameShot(camera_id=2, jpeg=b"b", captured_at=now, width=8, height=8),
    ]
    pipeline.submit(
        ConfirmedJob(
            room_id=room.id,
            alert_type="FIRE",
            started_at=now,
            sources=[],
            calibrations={},
            frames=frames,
            pump_observations=[
                {
                    "camera_id": 1,
                    "class_name": "fire",
                    "score": 0.9,
                    "effective_frames": 2,
                    "duration_ms": 100,
                }
            ],
            confirmed_monotonic=time.perf_counter(),
        )
    )
    assert analyzer.started.wait(2)
    time.sleep(0.05)
    assert sender.sent
    assert transport.commands == []
    analyzer.release.set()
    pipeline.wait()
    assert transport.commands
    pipeline.stop()
    pump.close()


def test_synthetic_frames_publish_events_while_qwen_is_delayed(tmp_path: Path, caplog) -> None:
    config = _config()
    engine = make_engine(f"sqlite:///{tmp_path / 'live.db'}")
    Base.metadata.create_all(engine)
    import fire_monitoring.models  # noqa: F401

    factory = make_session_factory(engine)
    session = factory()
    now = datetime.now(UTC)
    session.add(Room(name="101", scene_type="classroom", created_at=now))
    session.commit()
    room = session.query(Room).one()
    for index in range(4):
        session.add(
            Camera(
                name=f"摄像头{index + 1}",
                source_type="USB",
                source_uri=f"cam-{index}",
                stream_key=f"cam{index + 1}",
                target_fps=20,
                calibration_json=None if index == 3 else _calibration(),
                created_at=now,
            )
        )
    session.commit()
    cameras = session.query(Camera).order_by(Camera.id).all()
    for slot, camera in enumerate(cameras, start=1):
        session.add(RoomCamera(room_id=room.id, camera_id=camera.id, slot=slot))
    session.commit()

    detector = ScriptedDetector()
    analyzer = BlockingAnalyzer()
    sender = FakeSms()
    transport = FakeTransport()
    gate = FrameGate(np.zeros((48, 64, 3), dtype=np.uint8))
    seen: list[set[int]] = []

    def localizer(manifest) -> dict:
        from fire_monitoring_inference.localization import LocalizationInput

        request = LocalizationInput.model_validate_json(manifest.read_bytes())
        seen.append(set(request.views))
        return {
            "status": "ESTIMATED",
            "xyz": [1.0, 2.0, 0.0],
            "covariance": [[0.1, 0, 0], [0, 0.1, 0], [0, 0, 0.1]],
            "condition_number": 4.0,
            "support_camera_ids": sorted(request.views),
        }

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
    fatals: list[str] = []
    app = create_app(
        config,
        engine=engine,
        evidence=MemoryStore(),
        analyzer=analyzer,
        sms_sender=sender,
        pump=pump,
        detector=detector,
        open_capture=gate.open,
        localizer=localizer,
        on_fatal=lambda: fatals.append("fatal"),
    )
    caplog.set_level(logging.INFO, logger="fire_monitoring.alerts")
    with TestClient(app) as client:
        token = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "123456"}
        ).json()["access_token"]
        with client.websocket_connect(f"/api/v1/events?token={token}") as websocket:
            gate.go.set()
            popup = websocket.receive_json()
            assert popup["kind"] == "CONFIRMED"
            assert popup["room_name"] == "101"
            assert popup["alert_type"] == "FIRE"
            assert analyzer.started.wait(5)
            produced = len(detector.batches)
            time.sleep(0.3)
            assert len(detector.batches) > produced
            assert any(size == 4 for size in detector.batches)
            assert sender.sent
            assert transport.commands
            assert analyzer.release.is_set() is False
            analyzer.release.set()
            client.app.state.worker.pipeline.wait()
    assert fatals == []
    assert seen == [{cameras[0].id, cameras[1].id, cameras[2].id}]
    fresh = factory()
    alert = fresh.query(Alert).one()
    assert json.loads(alert.position_json)["status"] == "ESTIMATED"
    analysis = json.loads(alert.analysis_json)
    assert analysis["burning_objects"] == ["纸"]
    assert analysis["people_at_risk"] is False
    kinds = [row.kind for row in fresh.query(AlertEvent).order_by(AlertEvent.id)]
    assert kinds[0] == "CONFIRMED"
    assert kinds.index("SMS") < kinds.index("ANALYSIS")
    assert kinds.index("PUMP") < kinds.index("ANALYSIS")
    assert "LOCALIZED" in kinds
    assert any("popup" in record.message and "after confirmation" in record.message for record in caplog.records)
    pump.close()


def test_detection_failure_marks_health_down(tmp_path: Path) -> None:
    config = _config()
    engine = make_engine(f"sqlite:///{tmp_path / 'health.db'}")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    session = factory()
    now = datetime.now(UTC)
    session.add(Room(name="301", scene_type="classroom", created_at=now))
    session.commit()
    room = session.query(Room).one()
    session.add(
        Camera(
            name="摄像头",
            source_type="USB",
            source_uri="cam",
            stream_key="cam",
            target_fps=20,
            calibration_json=None,
            created_at=now,
        )
    )
    session.commit()
    camera = session.query(Camera).one()
    session.add(RoomCamera(room_id=room.id, camera_id=camera.id, slot=1))
    session.commit()
    gate = FrameGate(np.zeros((8, 8, 3), dtype=np.uint8))
    gate.go.set()
    app = create_app(
        config,
        engine=engine,
        evidence=MemoryStore(),
        detector=ExplodingDetector(),
        open_capture=gate.open,
        on_fatal=lambda: None,
        start_worker=True,
    )
    with TestClient(app) as client:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not client.app.state.worker.failed:
            time.sleep(0.02)
        assert client.app.state.worker.failed
        response = client.get("/api/v1/health")
        assert response.status_code == 503
        assert response.json()["detail"] == "detection stopped"
