from __future__ import annotations

READY = "READY FIRE_ACTUATOR_V2"
PAN_MIN, PAN_MAX = -12000, 12000
TILT_MIN, TILT_MAX = 0, 6000
RATE_CDEG_PER_MS = 9
MAX_RUN_MS = 30000
WATCHDOG_MS = 3000


def run_line(command_id: str, duration_ms: int) -> str:
    return f"RUN {command_id} {duration_ms}"


def _approach(current: int, target: int, step: int) -> int:
    delta = target - current
    if delta > step:
        return current + step
    if delta < -step:
        return current - step
    return target


class ActuatorDevice:
    """Host-side simulator of FIRE_ACTUATOR_V2. Button helpers apply the debounced result."""

    def __init__(self) -> None:
        self.now = 0
        self.running = False
        self.laser = False
        self.estop_held = False
        self.latched = False
        self.armed = False
        self.run_started = 0
        self.run_duration = 0
        self.last_host = 0
        self.last_id = "-"
        self.pan = 0
        self.tilt = 0
        self.pan_target = 0
        self.tilt_target = 0

    def advance(self, milliseconds: int) -> None:
        self.now += milliseconds
        step = milliseconds * RATE_CDEG_PER_MS
        self.pan = _approach(self.pan, self.pan_target, step)
        self.tilt = _approach(self.tilt, self.tilt_target, step)
        if self.running and self.now - self.run_started >= self.run_duration:
            self.running = False
        if self.now - self.last_host >= WATCHDOG_MS and (self.running or self.laser):
            self.running = False
            self.laser = False
            self.pan_target = self.pan
            self.tilt_target = self.tilt

    def latch_estop(self) -> None:
        self.estop_held = True
        self.latched = True
        self.armed = False
        self.running = False
        self.laser = False
        self.pan_target = self.pan
        self.tilt_target = self.tilt

    def release_estop(self) -> None:
        self.estop_held = False

    def press_reset(self) -> None:
        if self.latched and not self.estop_held:
            self.armed = True

    def exchange(self, line: str) -> str:
        self.advance(0)
        self.last_host = self.now
        if line == "HELLO":
            return READY
        if line == "PING":
            return "PONG"
        if line == "STATUS":
            return self._status()
        if line == "STOP":
            self.running = False
            self.laser = False
            self.pan_target = self.pan
            self.tilt_target = self.tilt
            return "STOPPED"
        if line == "UNLOCK":
            return self._unlock()
        if line.startswith("LASER "):
            return self._laser(line[6:])
        if line.startswith("AIM "):
            return self._aim(line[4:])
        if line.startswith("RUN "):
            return self._run(line[4:])
        return "ERR COMMAND"

    def _status(self) -> str:
        if not self.latched:
            latch = "CLEAR"
        elif self.armed and not self.estop_held:
            latch = "ARMED"
        else:
            latch = "LATCHED"
        return (
            f"STATE {'ON' if self.running else 'OFF'} {'ON' if self.laser else 'OFF'} "
            f"{latch} {self.pan} {self.tilt}"
        )

    def _unlock(self) -> str:
        if not self.latched:
            return "UNLOCKED"
        if self.estop_held:
            return "ERR ESTOP"
        if not self.armed:
            return "ERR RESET"
        self.latched = False
        self.armed = False
        return "UNLOCKED"

    def _laser(self, argument: str) -> str:
        if self.latched:
            return "ERR ESTOP"
        if argument == "ON":
            self.laser = True
            return "LASER ON"
        if argument == "OFF":
            self.laser = False
            return "LASER OFF"
        return "ERR FORMAT"

    def _aim(self, argument: str) -> str:
        if self.latched:
            return "ERR ESTOP"
        parts = argument.split(" ")
        if len(parts) != 2:
            return "ERR FORMAT"
        try:
            pan = int(parts[0])
            tilt = int(parts[1])
        except ValueError:
            return "ERR FORMAT"
        if not PAN_MIN <= pan <= PAN_MAX or not TILT_MIN <= tilt <= TILT_MAX:
            return "ERR LIMIT"
        self.pan_target = pan
        self.tilt_target = tilt
        return f"AIM {pan} {tilt}"

    def _run(self, argument: str) -> str:
        parts = argument.split(" ")
        if len(parts) != 2 or len(parts[0]) != 32 or any(c not in "0123456789abcdefABCDEF" for c in parts[0]):
            return "ERR FORMAT"
        if not parts[1].isdigit() or len(parts[1]) > 5:
            return "ERR DURATION"
        duration = int(parts[1])
        if not 100 <= duration <= MAX_RUN_MS:
            return "ERR DURATION"
        if self.latched:
            return "ERR ESTOP"
        command_id = parts[0]
        if command_id == self.last_id:
            return f"ACK {command_id} {'ON' if self.running else 'OFF'}"
        if self.running:
            return "ERR BUSY"
        self.last_id = command_id
        self.run_started = self.last_host = self.now
        self.run_duration = duration
        self.running = True
        return f"ACK {command_id} ON"
