from pathlib import Path

from fire_monitoring_inference.actuator_v2 import READY, ActuatorDevice, run_line
from fire_monitoring_inference.contracts import EventEnvelope, EventType, utc_now
from fire_monitoring_inference.pump import PumpConfig, PumpController


class SimTransport:
    def __init__(self, device: ActuatorDevice) -> None:
        self.device = device

    def prepare(self) -> None:
        if self.device.exchange("HELLO") != READY:
            raise OSError("unexpected pump firmware")

    def request(self, command: str) -> str:
        return self.device.exchange(command)

    def close(self) -> None:
        return None


def test_estop_rejects_run_until_reset_and_host_unlock() -> None:
    device = ActuatorDevice()
    command_id = "0123456789abcdef0123456789abcdef"
    assert device.exchange("HELLO") == READY
    assert device.exchange("AIM 13000 0") == "ERR LIMIT"
    assert device.exchange(run_line(command_id, 5000)) == f"ACK {command_id} ON"
    device.latch_estop()
    assert device.running is False
    assert device.exchange(run_line(command_id, 5000)) == "ERR ESTOP"
    device.release_estop()
    assert device.exchange("UNLOCK") == "ERR RESET"
    device.press_reset()
    assert device.exchange("UNLOCK") == "UNLOCKED"
    assert device.exchange(run_line(command_id, 1000)) == f"ACK {command_id} OFF"


def test_heartbeat_timeout_stops_pump_and_laser() -> None:
    device = ActuatorDevice()
    command_id = "abcdef0123456789abcdef0123456789"
    device.exchange(run_line(command_id, 20000))
    device.exchange("LASER ON")
    device.advance(2999)
    assert device.running is True
    assert device.laser is True
    device.advance(1)
    assert device.running is False
    assert device.laser is False


def test_controller_run_uses_the_same_device(tmp_path: Path) -> None:
    device = ActuatorDevice()
    now = utc_now()
    event = EventEnvelope.create(
        event_type=EventType.INCIDENT_CONFIRMED,
        source="server",
        zone_id=2,
        camera_id=1,
        payload={
            "dedupKey": "p3",
            "primaryType": "FIRE",
            "severity": "HIGH",
            "fusionMode": "SINGLE_CAMERA",
            "fusionScore": 0.9,
            "startedAt": now.isoformat(),
            "confirmedAt": now.isoformat(),
            "observations": [
                {
                    "cameraId": 1,
                    "viewRole": "SINGLE",
                    "className": "fire",
                    "score": 0.9,
                    "effectiveFrames": 3,
                    "durationMs": 400,
                }
            ],
        },
    )
    pump = PumpController(
        config=PumpConfig(
            enabled=True,
            port="SIM",
            zone_id=2,
            duration_ms=5000,
            cooldown_seconds=0,
            require_vlm=False,
            local_min_confidence=0.3,
            local_min_frames=1,
        ),
        journal_path=tmp_path / "pump.sqlite3",
        transport=SimTransport(device),
    )
    device.latch_estop()
    pump.trigger(event, None, captured_at=now)
    assert pump.snapshot()["records"][0]["reason"] == "ESTOP"
    assert device.running is False
    device.release_estop()
    device.press_reset()
    assert device.exchange("UNLOCK") == "UNLOCKED"
    pump.trigger(
        EventEnvelope.create(
            event_type=EventType.INCIDENT_CONFIRMED,
            source="server",
            zone_id=2,
            camera_id=1,
            payload=event.payload,
        ),
        None,
        captured_at=now,
    )
    assert device.running is True
    assert pump.snapshot()["records"][0]["status"] == "RUNNING"
    pump.close()


def test_aim_rate_limit() -> None:
    device = ActuatorDevice()
    assert device.exchange("AIM 9000 0") == "AIM 9000 0"
    device.advance(100)
    assert device.pan == 900
    assert device.tilt == 0
