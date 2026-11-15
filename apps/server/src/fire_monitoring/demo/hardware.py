from __future__ import annotations

import threading

from fire_monitoring_inference.actuator_v2 import ActuatorDevice
from fire_monitoring_inference.panel_v2 import PanelDevice


class DeviceLink:
    def __init__(self, device: ActuatorDevice | PanelDevice, step_ms: int = 0) -> None:
        self.device = device
        self.step_ms = step_ms
        self._lock = threading.Lock()

    def prepare(self) -> None:
        return None

    def request(self, command: str) -> str:
        with self._lock:
            if self.step_ms:
                self.device.advance(self.step_ms)
            return self.device.exchange(command)

    def close(self) -> None:
        return None
