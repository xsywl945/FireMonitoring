from __future__ import annotations

import re
import subprocess
import sys
import threading
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .live_frames import LiveFrameBuffer
from .runtime import RuntimeState


class CameraStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cameraId: int = Field(gt=0, strict=True)
    zoneId: int = Field(gt=0, strict=True)
    cameraIndex: int = Field(ge=0, le=99, strict=True)
    targetFps: float = Field(default=5, ge=1, le=30)


def local_devices() -> list[dict[str, Any]]:
    if sys.platform != "win32":
        raise RuntimeError("本机摄像头列表仅支持 Windows")
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
            capture_output=True,
            timeout=8,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("未找到 FFmpeg，可手动填写设备编号") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("读取摄像头列表超时") from exc
    names: list[str] = []
    lines = result.stderr.splitlines()
    for index, line in enumerate(lines):
        match = re.search(r'"([^"\r\n]+)"\s+\((video|none)\)', line)
        if match is None:
            continue
        # Some virtual video filters are reported as "none" by FFmpeg but still occupy
        # a DirectShow camera index. Keep them so later physical indices do not shift.
        alternate = lines[index + 1] if index + 1 < len(lines) else ""
        if match.group(2) == "video" or "860BB310" in alternate.upper():
            names.append(match.group(1))
    return [{"index": index, "name": name} for index, name in enumerate(names)]


class CameraControl:
    def __init__(
        self,
        *,
        worker: Callable[[CameraStart, threading.Event], None],
        runtime: RuntimeState,
        frames: LiveFrameBuffer,
        devices: Callable[[], list[dict[str, Any]]] = local_devices,
    ) -> None:
        self.worker = worker
        self.runtime = runtime
        self.frames = frames
        self.devices = devices
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self, request: CameraStart) -> dict[str, Any]:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("已有摄像头正在运行，请先停止")
            self.frames.clear()
            self._stop = threading.Event()
            self.runtime.prepare_camera(
                camera_id=request.cameraId,
                zone_id=request.zoneId,
                camera_index=request.cameraIndex,
            )
            self._thread = threading.Thread(
                target=self._run,
                args=(request, self._stop),
                daemon=True,
                name="live-camera-worker",
            )
            self._thread.start()
            return self.runtime.snapshot()

    def _run(self, request: CameraStart, stop: threading.Event) -> None:
        try:
            self.worker(request, stop)
        except Exception:
            self.runtime.fail("LIVE_CAMERA_START_FAILED")
        finally:
            self.frames.clear()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self._stop.set()
            if self._thread is not None:
                self._thread.join(timeout=3)
                if self._thread.is_alive():
                    raise RuntimeError("摄像头正在停止，请稍后重试")
            self.runtime.stop()
            self.frames.clear()
            return self.runtime.snapshot()
