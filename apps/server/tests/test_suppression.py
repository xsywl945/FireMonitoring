import json
from datetime import UTC, datetime
from pathlib import Path

from fire_monitoring_inference.actuator_v2 import ActuatorDevice
from fire_monitoring_inference.pump import PumpConfig, PumpController

from fire_monitoring.alerts.pipeline import AlertPipeline, ConfirmedJob
from fire_monitoring.config import AppConfig, load_config
from fire_monitoring.db import Base, make_engine, make_session_factory
from fire_monitoring.detection.ingest import FrameShot
from fire_monitoring.events.hub import EventHub
from fire_monitoring.evidence.store import MemoryStore
from fire_monitoring.models import Alert, AlertEvent, Room
from fire_monitoring.sms.service import SmsService
from fire_monitoring.suppression.service import SuppressionService

EXAMPLE = Path(__file__).resolve().parents[3] / "config.example.json"


class SimTransport:
    def __init__(self, device: ActuatorDevice) -> None:
        self.device = device

    def prepare(self) -> None:
        return None

    def request(self, command: str) -> str:
        return self.device.exchange(command)

    def close(self) -> None:
        return None


def _config() -> AppConfig:
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["llm"]["enabled"] = False
    data["sms"]["enabled"] = False
    config = AppConfig.model_validate(data)
    config.suppression.pending_seconds = 3
    config.suppression.clear_seconds = 3
    config.suppression.gimbal_path = "runtime/gimbal-test-absent.json"
    return config


def test_simulated_device_follows_confirm_aim_spray_and_extinguish(tmp_path: Path) -> None:
    config = _config()
    engine = make_engine(f"sqlite:///{tmp_path / 'suppress.db'}")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    session = factory()
    now = datetime.now(UTC)
    session.add(Room(name="101", scene_type="classroom", created_at=now))
    session.commit()
    room = session.query(Room).one()
    session.add(
        Alert(
            room_id=room.id,
            alert_type="FIRE",
            started_at=now,
            observations_json="[]",
            status="OPEN",
        )
    )
    session.commit()
    alert = session.query(Alert).one()
    device = ActuatorDevice()
    pump = PumpController(
        config=PumpConfig(
            enabled=True,
            port="SIM",
            zone_id=room.id,
            duration_ms=5000,
            cooldown_seconds=0,
            require_vlm=False,
            local_min_confidence=0.3,
            local_min_frames=1,
        ),
        journal_path=tmp_path / "pump.sqlite3",
        transport=SimTransport(device),
    )
    clock = [0.0]
    service = SuppressionService(
        config,
        factory,
        pump,
        EventHub(),
        clock=lambda: clock[0],
    )
    service.handle(
        ConfirmedJob(
            room_id=room.id,
            alert_type="FIRE",
            started_at=now,
            sources=[],
            calibrations={},
            frames=[],
            pump_observations=[
                {
                    "camera_id": 1,
                    "class_name": "fire",
                    "score": 0.9,
                    "effective_frames": 3,
                    "duration_ms": 400,
                }
            ],
            confirmed_monotonic=0,
            alert_id=alert.id,
            position={
                "status": "ESTIMATED",
                "xyz": [1.5, 2.5, 0.2],
                "covariance": [[0.0025, 0, 0], [0, 0.0025, 0], [0, 0, 0.0025]],
            },
        ),
        None,
    )
    assert service.machines[room.id].phase == "待喷"
    assert device.laser is True
    clock[0] = 3
    service.tick(room.id, flame_present=True, flame_area=80)
    assert service.machines[room.id].phase == "喷射"
    assert device.running is True
    clock[0] = 8
    service.tick(room.id, flame_present=False, flame_area=0)
    assert service.machines[room.id].phase == "复核"
    clock[0] = 11
    service.tick(room.id, flame_present=False, flame_area=0)
    assert service.machines[room.id].phase == "已扑灭"
    fresh = factory()
    phases = [
        json.loads(row.detail_json)["phase"]
        for row in fresh.query(AlertEvent).order_by(AlertEvent.id)
        if row.kind.startswith("SUP_")
    ]
    assert phases == ["已确认", "瞄准", "待喷", "喷射", "复核", "已扑灭"]
    spray = fresh.query(AlertEvent).filter_by(kind="SUP_SPRAY").one()
    detail = json.loads(spray.detail_json)
    assert detail["cover_probability"] >= detail["cover_threshold"]
    pump.close()


def test_electrical_room_blocks_water_without_qwen(tmp_path: Path) -> None:
    config = _config()
    config.suppression.pending_seconds = 0
    engine = make_engine(f"sqlite:///{tmp_path / 'prior.db'}")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    session = factory()
    now = datetime.now(UTC)
    session.add(Room(name="配电", scene_type="electrical_room", created_at=now))
    session.commit()
    room = session.query(Room).one()

    class Transport:
        def __init__(self) -> None:
            self.commands = []

        def prepare(self) -> None:
            return None

        def request(self, command: str) -> str:
            self.commands.append(command)
            if command == "STATUS":
                return "STATE OFF OFF CLEAR 0 0"
            if command.startswith("RUN "):
                return f"ACK {command.split()[1]} ON"
            return command

        def close(self) -> None:
            return None

    transport = Transport()
    pump = PumpController(
        config=PumpConfig(
            enabled=True,
            port="SIM",
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
    pipeline = AlertPipeline(
        config,
        factory,
        MemoryStore(),
        None,
        SmsService(config, None),
        pump,
        EventHub(),
        localizer=lambda _manifest: {
            "status": "ESTIMATED",
            "xyz": [1.5, 2.5, 0.2],
            "covariance": [[0.0025, 0, 0], [0, 0.0025, 0], [0, 0, 0.0025]],
            "condition_number": 1,
            "support_camera_ids": [1, 2],
        },
        on_fatal=lambda: None,
    )
    pipeline.start()
    pipeline.submit(
        ConfirmedJob(
            room_id=room.id,
            alert_type="FIRE",
            started_at=now,
            sources=[],
            calibrations={},
            frames=[FrameShot(camera_id=1, jpeg=b"a", captured_at=now, width=8, height=8)],
            pump_observations=[
                {
                    "camera_id": 1,
                    "class_name": "fire",
                    "score": 0.9,
                    "effective_frames": 3,
                    "duration_ms": 400,
                }
            ],
            confirmed_monotonic=0,
        )
    )
    pipeline.wait()
    pipeline.stop()
    assert not any(item.startswith("RUN ") for item in transport.commands)
    reason = json.loads(session.query(AlertEvent).filter_by(kind="SUP_BLOCK").one().detail_json)
    assert reason["reason"] == "WATER_PROHIBITED"
    pump.close()
