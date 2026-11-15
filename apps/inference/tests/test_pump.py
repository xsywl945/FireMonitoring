import threading
from datetime import timedelta

from fire_monitoring_inference.contracts import utc_now
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
        if command == "STATUS":
            pump = "ON" if self.active != "-" else "OFF"
            return f"STATE {pump} OFF CLEAR 0 0"
        if command == "HELLO":
            return "READY FIRE_ACTUATOR_V2"
        return "ERR COMMAND"

    def close(self):
        pass


def test_dispatch_runs_once_and_a_restart_does_not_repeat_it(tmp_path):
    device = Device()
    config = PumpConfig(enabled=True, port="COM4", zone_id=2)
    path = tmp_path / "pump.sqlite3"
    pump = PumpController(config=config, transport=device, journal_path=path)
    trace = "0123456789abcdef0123456789abcdef"
    pump.dispatch_run(trace, 5000, captured_at=utc_now())
    pump.dispatch_run(trace, 5000, captured_at=utc_now())
    assert [item for item in device.commands if item.startswith("RUN ")] == [f"RUN {trace} 5000"]
    assert pump.snapshot()["records"][0]["status"] == "RUNNING"
    restarted = PumpController(config=config, transport=device, journal_path=path)
    restarted.dispatch_run(trace, 5000, captured_at=utc_now())
    assert len([item for item in device.commands if item.startswith("RUN ")]) == 1
    assert restarted.snapshot()["records"][0]["status"] == "UNKNOWN"


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
    trace = "abcdef0123456789abcdef0123456789"
    pump.dispatch_run(trace, 5000, captured_at=utc_now())
    pump.dispatch_run(trace, 5000, captured_at=utc_now())
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


def test_serial_reconnect_cannot_start_expired_or_stopped_camera(tmp_path):
    current = [utc_now()]
    captured_at = current[0] - timedelta(seconds=29)
    cancelled = threading.Event()

    class SlowConnect(Device):
        def prepare(self):
            current[0] += timedelta(seconds=2)
            cancelled.set()

    device = SlowConnect()
    pump = PumpController(
        config=PumpConfig(enabled=True, port="COM4", zone_id=2),
        transport=device,
        journal_path=tmp_path / "pump.sqlite3",
        clock=lambda: current[0],
    )
    record = pump.dispatch_run(
        "0123456789abcdef0123456789abcdef",
        5000,
        captured_at=captured_at,
        cancelled=cancelled,
    )
    assert record["reason"] == "CAMERA_STOPPED"
    assert not any(item.startswith("RUN ") for item in device.commands)


def test_refresh_marks_a_finished_run(tmp_path):
    device = Device()
    pump = PumpController(
        config=PumpConfig(enabled=True, port="COM4", zone_id=2, cooldown_seconds=0),
        transport=device,
        journal_path=tmp_path / "pump.sqlite3",
    )
    pump.dispatch_run("0123456789abcdef0123456789abcdef", 5000, captured_at=utc_now())
    device.active = "-"
    pump.refresh()
    assert pump.snapshot()["records"][0]["status"] == "STOPPED"
