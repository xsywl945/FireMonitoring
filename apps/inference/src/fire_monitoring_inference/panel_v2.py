from __future__ import annotations

import threading
import time

READY = "READY FIRE_PANEL_V2"
MODES = {"OFF", "GREEN", "YELLOW", "RED_BLINK", "RED_SOLID", "ALT"}
WATCHDOG_MS = 3000


class PanelDevice:
    """Host-side simulator of FIRE_PANEL_V2."""

    def __init__(self) -> None:
        self.now = 0
        self.host_mode = "OFF"
        self.link_up = True
        self.mute = False
        self.last_host = 0

    def advance(self, milliseconds: int) -> None:
        self.now += milliseconds
        if self.link_up and self.now - self.last_host >= WATCHDOG_MS:
            self.link_up = False

    def press_mute(self) -> None:
        self.mute = not self.mute

    def effective_mode(self) -> str:
        return self.host_mode if self.link_up else "ALT"

    def exchange(self, line: str) -> str:
        self.advance(0)
        self.last_host = self.now
        self.link_up = True
        if line == "HELLO":
            return READY
        if line == "PING":
            return "PONG"
        if line == "STATUS":
            return f"STATE {self.effective_mode()} {'MUTE' if self.mute else 'OPEN'} UP"
        if line.startswith("MODE "):
            name = line[5:]
            if name not in MODES:
                return "ERR MODE"
            self.host_mode = name
            return f"MODE {name}"
        return "ERR COMMAND"


class SerialLineTransport:
    def __init__(self, port: str, ready: str) -> None:
        self.port = port
        self.ready = ready
        self._serial = None

    def prepare(self) -> None:
        try:
            if self._serial is None:
                import serial

                self._serial = serial.Serial(self.port, 115200, timeout=0.2, write_timeout=1)
                time.sleep(2)
                self._serial.reset_input_buffer()
                if self.exchange("HELLO") != self.ready:
                    raise OSError("unexpected firmware")
        except Exception:
            self.close()
            raise

    def exchange(self, command: str) -> str:
        if self._serial is None:
            raise OSError("serial port is closed")
        data = (command + "\n").encode("ascii")
        if self._serial.write(data) != len(data):
            raise OSError("incomplete serial write")
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            line = self._serial.readline(160).decode("ascii", errors="replace").strip()
            if line:
                return line
        raise TimeoutError("serial acknowledgement timed out")

    def request(self, command: str) -> str:
        try:
            self.prepare()
            return self.exchange(command)
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None


class PanelLink:
    def __init__(self, port: str, transport=None) -> None:
        self.transport = transport or SerialLineTransport(port, READY)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.transport.prepare()
        if self.transport.request("MODE GREEN") != "MODE GREEN":
            raise OSError("panel rejected GREEN")
        self._thread = threading.Thread(target=self._run, name="panel-link", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                if self.transport.request("PING") != "PONG":
                    raise OSError("panel lost")
            except Exception:
                self.transport.close()
            self._stop.wait(0.5)

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self.transport.close()
