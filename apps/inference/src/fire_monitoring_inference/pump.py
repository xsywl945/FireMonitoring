from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field, model_validator

from .actuator_v2 import READY, run_line
from .contracts import utc_now


class PumpConfig(BaseModel):
    enabled: bool = False
    port: str = ""
    zone_id: int | None = Field(default=None, gt=0)
    duration_ms: int = Field(default=5000, ge=100, le=30_000)
    cooldown_seconds: int = Field(default=0, ge=0, le=3600)
    min_confidence: float = Field(default=0.7, ge=0, le=1)
    max_evidence_age_seconds: int = Field(default=30, ge=1, le=60)
    require_vlm: bool = True
    local_min_confidence: float = Field(default=0.45, ge=0, le=1)
    local_min_frames: int = Field(default=3, ge=1, le=100)

    @model_validator(mode="after")
    def configured(self) -> PumpConfig:
        if self.enabled and (not self.port.strip() or self.zone_id is None):
            raise ValueError("PUMP_ENABLED requires PUMP_SERIAL_PORT and PUMP_ZONE_ID")
        return self


class PumpTransport(Protocol):
    def prepare(self) -> None: ...
    def request(self, command: str) -> str: ...
    def close(self) -> None: ...


class SerialPumpTransport:
    """One persistent USB connection; commands are never retried after an uncertain write."""

    def __init__(self, port: str) -> None:
        self.port = port
        self._serial = None

    def prepare(self) -> None:
        try:
            if self._serial is None:
                import serial

                self._serial = serial.Serial(
                    self.port,
                    115200,
                    timeout=0.2,
                    write_timeout=1,
                )
                # Opening CH340 may reset the board. Never send RUN before the handshake.
                time.sleep(2)
                self._serial.reset_input_buffer()
                if self._exchange("HELLO") != READY:
                    raise OSError("unexpected pump firmware")
        except Exception:
            self.close()
            raise

    def request(self, command: str) -> str:
        try:
            self.prepare()
            return self._exchange(command)
        except Exception:
            self.close()
            raise

    def _exchange(self, command: str) -> str:
        assert self._serial is not None
        data = (command + "\n").encode("ascii")
        if self._serial.write(data) != len(data):
            raise OSError("incomplete pump write")
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            line = self._serial.readline(160).decode("ascii", errors="replace").strip()
            if line:
                return line
        raise TimeoutError("pump acknowledgement timed out")

    def close(self) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None


class PumpController:
    """Shared by both cameras. SQLite claims survive restart and suppress replays."""

    def __init__(
        self,
        *,
        config: PumpConfig,
        journal_path: Path,
        transport: PumpTransport | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.config = config
        self.transport = transport or SerialPumpTransport(config.port)
        self.clock = clock
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._inhibited = False
        self._connected = False
        self._device_state = "UNKNOWN" if config.enabled else "DISABLED"
        self._error: str | None = None
        self._activation_source: str | None = None
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(journal_path, check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS commands (trace TEXT PRIMARY KEY, data TEXT)")
        for record in self._records():
            if record["status"] in {"ATTEMPTING", "RUNNING"}:
                record.update(status="UNKNOWN", reason="SERVICE_RESTARTED")
                self._save(record)

    def _records(self) -> list[dict]:
        return [
            json.loads(row[0])
            for row in self._db.execute("SELECT data FROM commands ORDER BY rowid DESC")
        ]

    def _save(self, record: dict) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO commands VALUES (?, ?)", (record["traceId"], json.dumps(record))
        )
        self._db.commit()

    def _live_rejection(
        self, captured_at: datetime, cancelled: threading.Event | None
    ) -> str | None:
        if cancelled is not None and cancelled.is_set():
            return "CAMERA_STOPPED"
        if self._inhibited:
            return "EMERGENCY_STOP_LATCHED"
        age = (self.clock() - captured_at).total_seconds()
        if not 0 <= age <= self.config.max_evidence_age_seconds:
            return "STALE_EVIDENCE"
        return None

    def command(self, line: str) -> str:
        with self._lock:
            reply = self.transport.request(line)
            self._connected = True
            return reply

    def release_inhibit(self) -> None:
        self._inhibited = False

    def dispatch_run(
        self,
        trace_id: str,
        duration_ms: int,
        *,
        captured_at: datetime,
        cancelled: threading.Event | None = None,
        zone_id: int | None = None,
        camera_id: int | None = None,
    ) -> dict:
        with self._lock:
            if self._db.execute("SELECT 1 FROM commands WHERE trace = ?", (trace_id,)).fetchone():
                return json.loads(
                    self._db.execute("SELECT data FROM commands WHERE trace = ?", (trace_id,)).fetchone()[0]
                )
            now = self.clock()
            reason = self._live_rejection(captured_at, cancelled)
            if reason is None and not self.config.enabled:
                reason = "PUMP_DISABLED"
            record = dict(
                traceId=trace_id,
                zoneId=zone_id if zone_id is not None else self.config.zone_id,
                cameraId=camera_id,
                createdAt=now.isoformat(),
                durationMs=duration_ms,
                status="SKIPPED" if reason else "ATTEMPTING",
                reason=reason,
            )
            if reason:
                self._save(record)
                return record
            # Commit before writing: an ambiguous timeout must never cause another RUN.
            record["attemptedAt"] = now.isoformat()
            self._save(record)
            try:
                self.transport.prepare()
                reason = self._live_rejection(captured_at, cancelled)
                if reason is not None:
                    record.update(status="SKIPPED", reason=reason)
                    record.pop("attemptedAt", None)
                    self._save(record)
                    return record
                reply = self.transport.request(run_line(trace_id, duration_ms))
                if reply.startswith("ERR "):
                    record.update(status="SKIPPED", reason=reply.split()[1])
                    record.pop("attemptedAt", None)
                    self._connected = True
                    self._device_state = "OFF"
                    self._error = reply.split()[1]
                    self._save(record)
                    return record
                if reply != f"ACK {trace_id} ON":
                    raise OSError("pump did not acknowledge this command")
                record.update(status="RUNNING", reason=None)
                self._connected = True
                self._device_state = "ON"
                self._activation_source = "AUTO"
                self._error = None
            except Exception:
                record.update(status="UNKNOWN", reason="DEVICE_ACK_UNAVAILABLE")
                self._connected = False
                self._device_state = "UNKNOWN"
                self._error = "DEVICE_ACK_UNAVAILABLE"
            self._save(record)
            return record

    def cutoff(self) -> None:
        with self._lock:
            if not self.config.enabled:
                return
            if self.transport.request("STOP") != "STOPPED":
                raise OSError("stop not acknowledged")
            self._device_state = "OFF"
            self._activation_source = None
            self._connected = True

    def refresh(self) -> None:
        if not self.config.enabled:
            return
        with self._lock:
            try:
                reply = self.transport.request("STATUS")
                parts = reply.split()
                if len(parts) != 6 or parts[0] != "STATE" or parts[1] not in {"ON", "OFF"}:
                    raise OSError("invalid pump status")
                if self._inhibited and parts[1] == "ON":
                    self.emergency_stop()
                    return
                self._device_state = parts[1]
                self._activation_source = "AUTO" if parts[1] == "ON" else None
                self._connected = True
                self._error = None
                for record in self._records():
                    if record["status"] == "RUNNING" and parts[1] == "OFF":
                        record.update(
                            status="STOPPED",
                            reason="DEVICE_REPORTED_OFF",
                            stoppedAt=self.clock().isoformat(),
                        )
                        self._save(record)
            except Exception:
                self._connected = False
                self._device_state = "UNKNOWN"
                self._error = "DEVICE_STATUS_UNAVAILABLE"

    def emergency_stop(self) -> dict:
        # Latch immediately, including while a camera is waiting for a serial reconnect.
        self._inhibited = True
        with self._lock:
            if self.config.enabled:
                try:
                    if self.transport.request("STOP") != "STOPPED":
                        raise OSError("stop not acknowledged")
                    self._device_state = "OFF"
                    self._activation_source = None
                    self._connected = True
                    self._error = None
                    for record in self._records():
                        if record["status"] == "RUNNING":
                            record.update(
                                status="STOPPED",
                                reason="EMERGENCY_STOP",
                                stoppedAt=self.clock().isoformat(),
                            )
                            self._save(record)
                except Exception:
                    self._device_state = "UNKNOWN"
                    self._connected = False
                    self._error = "STOP_ACK_UNAVAILABLE"
            return self.snapshot()

    def snapshot(self) -> dict:
        with self._lock:
            return dict(
                enabled=self.config.enabled,
                zoneId=self.config.zone_id,
                connected=self._connected,
                deviceState=self._device_state,
                inhibited=self._inhibited,
                lastError=self._error,
                durationMs=self.config.duration_ms,
                cooldownSeconds=self.config.cooldown_seconds,
                records=self._records()[:100],
                recognitionMode="VLM" if self.config.require_vlm else "LOCAL_YOLO",
                activationSource=self._activation_source,
            )

    def start(self) -> None:
        def monitor() -> None:
            while not self._stop.is_set():
                self.refresh()
                self._stop.wait(0.5)

        self._thread = threading.Thread(target=monitor, name="pump-status", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        with self._lock:
            self.emergency_stop()
            self.transport.close()
            self._db.close()
