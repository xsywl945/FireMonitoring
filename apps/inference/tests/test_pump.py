import threading
from datetime import timedelta

import pytest
from test_enrichment import FakeReasoner, _gate_job

from fire_monitoring_inference.contracts import utc_now
from fire_monitoring_inference.pump import PumpConfig, PumpController


class Device:
    def __init__(self):
        self.commands = []
        self.active = "-"

    def request(self, command):
        self.commands.append(command)
        if command.startswith("RUN "):
            self.active = command.split()[1]
            return f"ACK {self.active} ON"
        if command == "STOP":
            self.active = "-"
            return "STOPPED"
        return f"STATE {'ON' if self.active != '-' else 'OFF'} {self.active}"

    def close(self):
        pass


def test_positive_live_judgement_runs_once_and_persists_before_restart(tmp_path):
    device = Device()
    config = PumpConfig(enabled=True, port="COM4", zone_id=2)
    path = tmp_path / "pump.sqlite3"
    pump = PumpController(config=config, transport=device, journal_path=path)
    job = _gate_job()
    judgement = FakeReasoner().analyze(
        incident_id=None, image_data_urls=["data:image/jpeg;base64,a"]
    )
    pump.trigger(job.confirmed, judgement, captured_at=utc_now())
    pump.trigger(job.confirmed, judgement, captured_at=utc_now())
    assert [x for x in device.commands if x.startswith("RUN ")] == [
        f"RUN {job.confirmed.trace_id.hex} 5000"
    ]
    assert pump.snapshot()["records"][0]["status"] == "RUNNING"
    restarted = PumpController(config=config, transport=device, journal_path=path)
    restarted.trigger(job.confirmed, judgement, captured_at=utc_now())
    assert len([x for x in device.commands if x.startswith("RUN ")]) == 1
    assert restarted.snapshot()["records"][0]["status"] == "UNKNOWN"


def test_pump_rejects_stale_or_negative_judgement(tmp_path):
    device = Device()
    pump = PumpController(
        config=PumpConfig(enabled=True, port="COM4", zone_id=2),
        transport=device,
        journal_path=tmp_path / "pump.sqlite3",
    )
    job = _gate_job()
    judgement = FakeReasoner().analyze(
        incident_id=None, image_data_urls=["data:image/jpeg;base64,a"]
    )
    pump.trigger(job.confirmed, judgement, captured_at=utc_now() - timedelta(minutes=2))
    assert pump.snapshot()["records"][0]["reason"] == "STALE_EVIDENCE"
    negative = judgement.model_copy(update={"has_visible_fire": False})
    pump.trigger(_gate_job().confirmed, negative, captured_at=utc_now())
    assert not any(x.startswith("RUN ") for x in device.commands)


@pytest.mark.parametrize(
    "case,reason",
    [
        ("disabled", "PUMP_DISABLED"),
        ("other_room", "ZONE_NOT_COVERED"),
        ("failed_vlm", "VLM_NOT_CONFIRMED"),
        ("low_confidence", "VLM_NOT_CONFIRMED"),
        ("cancelled", "CAMERA_STOPPED"),
        ("emergency", "EMERGENCY_STOP_LATCHED"),
    ],
)
def test_unqualified_events_never_run_pump(tmp_path, case, reason):
    device = Device()
    pump = PumpController(
        config=PumpConfig(
            enabled=case != "disabled", port="COM4", zone_id=99 if case == "other_room" else 2
        ),
        transport=device,
        journal_path=tmp_path / "pump.sqlite3",
    )
    judgement = FakeReasoner().analyze(
        incident_id=None, image_data_urls=["data:image/jpeg;base64,a"]
    )
    if case == "failed_vlm":
        judgement = judgement.model_copy(update={"status": "FAILED"})
    if case == "low_confidence":
        judgement = judgement.model_copy(update={"confidence": 0.5})
    cancelled = threading.Event()
    if case == "cancelled":
        cancelled.set()
    if case == "emergency":
        pump.emergency_stop()
    pump.trigger(_gate_job().confirmed, judgement, captured_at=utc_now(), cancelled=cancelled)
    assert pump.snapshot()["records"][0]["reason"] == reason
    assert not any(x.startswith("RUN ") for x in device.commands)


def test_two_views_share_cooldown_and_only_device_off_completes_record(tmp_path):
    device = Device()
    pump = PumpController(
        config=PumpConfig(enabled=True, port="COM4", zone_id=2),
        transport=device,
        journal_path=tmp_path / "pump.sqlite3",
    )
    judgement = FakeReasoner().analyze(
        incident_id=None, image_data_urls=["data:image/jpeg;base64,a"]
    )
    pump.trigger(_gate_job().confirmed, judgement, captured_at=utc_now())
    pump.trigger(_gate_job().confirmed, judgement, captured_at=utc_now())
    assert pump.snapshot()["records"][0]["reason"] == "COOLDOWN"
    device.active = "-"
    pump.refresh()
    assert any(r["status"] == "STOPPED" for r in pump.snapshot()["records"])
    assert len([x for x in device.commands if x.startswith("RUN ")]) == 1


def test_uncertain_ack_is_recorded_and_not_retried(tmp_path):
    class LostAck(Device):
        def request(self, command):
            super().request(command)
            raise TimeoutError()

    device = LostAck()
    pump = PumpController(
        config=PumpConfig(enabled=True, port="COM4", zone_id=2),
        transport=device,
        journal_path=tmp_path / "pump.sqlite3",
    )
    job = _gate_job()
    judgement = FakeReasoner().analyze(
        incident_id=None, image_data_urls=["data:image/jpeg;base64,a"]
    )
    pump.trigger(job.confirmed, judgement, captured_at=utc_now())
    pump.trigger(job.confirmed, judgement, captured_at=utc_now())
    assert pump.snapshot()["records"][0]["status"] == "UNKNOWN"
    assert len(device.commands) == 1


def test_pump_http_status_and_emergency_stop_require_control_token(tmp_path):
    from fire_monitoring_inference.api import create_app

    pump = PumpController(
        config=PumpConfig(), transport=Device(), journal_path=tmp_path / "pump.sqlite3"
    )
    client = create_app(pump=pump).test_client()
    assert client.get("/api/v1/pump").status_code == 403
    assert client.post("/api/v1/pump/stop").status_code == 403
    headers = {"X-Control-Token": "local-camera-control"}
    assert client.get("/api/v1/pump", headers=headers).json["enabled"] is False
    assert client.post("/api/v1/pump/stop", headers=headers).json["inhibited"] is True


def test_emergency_stop_keeps_retrying_safe_stop_until_device_confirms_off(tmp_path):
    class MissedStop(Device):
        lost = True

        def request(self, command):
            if command == "STOP" and self.lost:
                self.commands.append(command)
                raise TimeoutError()
            return super().request(command)

    device = MissedStop()
    device.active = "0123456789abcdef0123456789abcdef"
    pump = PumpController(
        config=PumpConfig(enabled=True, port="COM4", zone_id=2),
        transport=device,
        journal_path=tmp_path / "pump.sqlite3",
    )
    assert pump.emergency_stop()["lastError"] == "STOP_ACK_UNAVAILABLE"
    pump.refresh()
    assert pump.snapshot()["lastError"] == "STOP_ACK_UNAVAILABLE"
    device.lost = False
    pump.refresh()
    assert pump.snapshot()["deviceState"] == "OFF"
    assert pump.snapshot()["inhibited"] is True
