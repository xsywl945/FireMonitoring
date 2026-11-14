import threading
from datetime import timedelta

import pytest

from fire_monitoring_inference.contracts import EventEnvelope, EventType, VlmAnalysisPayload, utc_now
from fire_monitoring_inference.pump import PumpConfig, PumpController


class Device:
    def __init__(self):
        self.commands = []
        self.active = "-"

    def prepare(self):
        pass

    def request(self, command):
        self.commands.append(command)
        if command.startswith("RUN "):
            self.active = command.split()[1]
            return f"ACK {self.active} ON"
        if command == "STOP":
            self.active = "-"
            return "STOPPED"
        if command == "STATUS" or command == "HELLO":
            pump = "ON" if self.active != "-" else "OFF"
            return f"STATE {pump} OFF CLEAR 0 0" if command == "STATUS" else "READY FIRE_ACTUATOR_V2"
        return "ERR COMMAND"

    def close(self):
        pass


def local_fire_event(primary_type="FIRE"):
    now = utc_now()
    return EventEnvelope.create(
        event_type=EventType.INCIDENT_CONFIRMED,
        source="live-yolo",
        site_id=1,
        zone_id=2,
        camera_id=3,
        model_version="real-yolo-test",
        payload={
            "dedupKey": "local-fire-test",
            "primaryType": primary_type,
            "severity": "HIGH",
            "fusionMode": "SINGLE_CAMERA",
            "fusionScore": 0.84,
            "startedAt": (now - timedelta(milliseconds=400)).isoformat(),
            "confirmedAt": now.isoformat(),
            "observations": [
                {
                    "cameraId": 3,
                    "viewRole": "SINGLE",
                    "className": "smoke" if primary_type == "SMOKE" else "fire",
                    "score": 0.84,
                    "effectiveFrames": 3,
                    "durationMs": 400,
                }
            ],
        },
    )


class FakeReasoner:
    def analyze(self, *, incident_id: int | None, image_data_urls: list[str]) -> VlmAnalysisPayload:
        assert incident_id is None
        assert image_data_urls[0].startswith("data:image/jpeg;base64,")
        return VlmAnalysisPayload(
            status="SUCCEEDED",
            provider="dashscope",
            model="qwen3.7-plus",
            promptVersion="fire-evidence-v4",
            hasVisibleFire=True,
            hasVisibleSmoke=False,
            waterProhibited=False,
        )


class _Gate:
    def __init__(self, confirmed: EventEnvelope) -> None:
        self.confirmed = confirmed


def _gate_job() -> _Gate:
    return _Gate(local_fire_event())


def test_local_confirmed_fire_runs_without_cloud_judgement(tmp_path):
    device = Device()
    pump = PumpController(
        config=PumpConfig(enabled=True, port="COM14", zone_id=2, require_vlm=False),
        transport=device,
        journal_path=tmp_path / "pump.sqlite3",
    )
    event = local_fire_event()
    pump.trigger(event, None, captured_at=utc_now())
    assert device.commands == [f"RUN {event.trace_id.hex} 5000"]
    assert pump.snapshot()["recognitionMode"] == "LOCAL_YOLO"


def test_disabled_cooldown_allows_new_fire_immediately_after_device_stops(tmp_path):
    device = Device()
    pump = PumpController(
        config=PumpConfig(enabled=True, port="COM14", zone_id=2, require_vlm=False),
        transport=device,
        journal_path=tmp_path / "pump.sqlite3",
    )
    first = local_fire_event()
    second = local_fire_event()
    pump.trigger(first, None, captured_at=utc_now())
    device.active = "-"
    pump.refresh()
    pump.trigger(second, None, captured_at=utc_now())
    pump.trigger(second, None, captured_at=utc_now())
    assert [cmd for cmd in device.commands if cmd.startswith("RUN ")] == [
        f"RUN {first.trace_id.hex} 5000", f"RUN {second.trace_id.hex} 5000"
    ]
    assert pump.snapshot()["cooldownSeconds"] == 0


def test_smoke_only_event_does_not_start_local_pump(tmp_path):
    device = Device()
    pump = PumpController(
        config=PumpConfig(enabled=True, port="COM14", zone_id=2, require_vlm=False),
        transport=device,
        journal_path=tmp_path / "pump.sqlite3",
    )
    pump.trigger(local_fire_event("SMOKE"), None, captured_at=utc_now())
    assert device.commands == []
    assert pump.snapshot()["records"][0]["reason"] == "LOCAL_FIRE_NOT_CONFIRMED"


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
    cancelled = threading.Event()
    if case == "cancelled":
        cancelled.set()
    if case == "emergency":
        pump.emergency_stop()
    pump.trigger(_gate_job().confirmed, judgement, captured_at=utc_now(), cancelled=cancelled)
    assert pump.snapshot()["records"][0]["reason"] == reason
    assert not any(x.startswith("RUN ") for x in device.commands)


@pytest.mark.parametrize(
    "overrides",
    [
        {"energized_equipment": True, "suspected_cause": "electrical_short"},
        {"liquid": True, "burning_objects": []},
        {"metal_powder": True, "burning_objects": []},
        {"oil_pan": True, "suspected_cause": "cooking_oil", "burning_objects": []},
    ],
)
def test_water_prohibited_classes_never_start_the_pump(tmp_path, overrides):
    from fire_monitoring_inference.analysis.rules import classify

    evidence = {
        "burning_objects": [{"frame_index": 1, "name": "纸", "evidence": "画面1"}],
        "suspected_cause": "open_flame",
        "energized_equipment": False,
        "liquid": False,
        "oil_pan": False,
        "metal_powder": False,
        "person_count": 0,
        "person_location": "",
        "scene_type": "classroom",
        "smoke_color": "none",
        "smoke_density": "none",
        "uncertainties": [],
    }
    evidence.update(overrides)
    resolved = classify(evidence, "classroom")
    assert resolved["water_prohibited"] is True
    device = Device()
    pump = PumpController(
        config=PumpConfig(enabled=True, port="COM4", zone_id=2),
        transport=device,
        journal_path=tmp_path / "pump.sqlite3",
    )
    judgement = FakeReasoner().analyze(
        incident_id=None, image_data_urls=["data:image/jpeg;base64,a"]
    ).model_copy(
        update={
            "water_prohibited": resolved["water_prohibited"],
            "has_visible_fire": True,
        }
    )
    pump.trigger(_gate_job().confirmed, judgement, captured_at=utc_now())
    assert pump.snapshot()["records"][0]["reason"] == "WATER_PROHIBITED"
    assert not any(x.startswith("RUN ") for x in device.commands)


def test_two_views_share_cooldown_and_only_device_off_completes_record(tmp_path):
    device = Device()
    pump = PumpController(
        config=PumpConfig(enabled=True, port="COM4", zone_id=2, cooldown_seconds=60),
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


@pytest.mark.parametrize(
    "case,reason",
    [
        ("stale", "STALE_EVIDENCE"),
        ("cancelled", "CAMERA_STOPPED"),
    ],
)
def test_serial_reconnect_cannot_start_expired_or_stopped_camera(tmp_path, case, reason):
    current = [utc_now()]
    captured_at = current[0] - timedelta(seconds=29)
    cancelled = threading.Event()

    class SlowConnect(Device):
        def prepare(self):
            current[0] += timedelta(seconds=2)
            if case == "cancelled":
                cancelled.set()

    device = SlowConnect()
    pump = PumpController(
        config=PumpConfig(enabled=True, port="COM4", zone_id=2),
        transport=device,
        journal_path=tmp_path / "pump.sqlite3",
        clock=lambda: current[0],
    )
    judgement = FakeReasoner().analyze(
        incident_id=None, image_data_urls=["data:image/jpeg;base64,a"]
    )
    pump.trigger(_gate_job().confirmed, judgement, captured_at=captured_at, cancelled=cancelled)
    assert pump.snapshot()["records"][0]["reason"] == reason
    assert not any(x.startswith("RUN ") for x in device.commands)
