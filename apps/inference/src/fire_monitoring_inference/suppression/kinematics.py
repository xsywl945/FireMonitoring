from __future__ import annotations

from dataclasses import dataclass

import numpy as np

PAN_MIN, PAN_MAX = -12000, 12000
TILT_MIN, TILT_MAX = 0, 6000
NOMINAL_SCALE = float(np.deg2rad(0.01))


def _rx(angle: float) -> np.ndarray:
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def _ry(angle: float) -> np.ndarray:
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def _rz(angle: float) -> np.ndarray:
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


@dataclass
class GimbalParams:
    """Eleven scalars. World axes are the calibration control-point frame, metres, z up."""

    p0: np.ndarray
    yaw: float
    roll: float
    pitch: float
    pan_scale: float
    pan_zero: float
    tilt_scale: float
    tilt_zero: float
    nozzle_offset: float

    def __post_init__(self) -> None:
        self.p0 = np.asarray(self.p0, dtype=float).reshape(3)

    def base(self) -> np.ndarray:
        return _rz(self.yaw) @ _ry(self.pitch) @ _rx(self.roll)

    def pose(self, pan_rad: float, tilt_rad: float) -> tuple[np.ndarray, np.ndarray]:
        mounted = self.base() @ _rz(pan_rad)
        direction = mounted @ np.array([np.cos(tilt_rad), 0.0, np.sin(tilt_rad)])
        origin = self.p0 + mounted @ np.array([self.nozzle_offset, 0.0, 0.0])
        return origin, direction / np.linalg.norm(direction)

    def ray(self, pan_cdeg: float, tilt_cdeg: float) -> tuple[np.ndarray, np.ndarray]:
        pan = self.pan_scale * (pan_cdeg - self.pan_zero)
        tilt = self.tilt_scale * (tilt_cdeg - self.tilt_zero)
        return self.pose(pan, tilt)

    def command(self, pan_rad: float, tilt_rad: float) -> tuple[int, int] | None:
        pan = int(round(pan_rad / self.pan_scale + self.pan_zero))
        tilt = int(round(tilt_rad / self.tilt_scale + self.tilt_zero))
        if not PAN_MIN <= pan <= PAN_MAX or not TILT_MIN <= tilt <= TILT_MAX:
            return None
        return pan, tilt

    def tilt_window(self) -> tuple[float, float]:
        low = self.tilt_scale * (TILT_MIN - self.tilt_zero)
        high = self.tilt_scale * (TILT_MAX - self.tilt_zero)
        return (low, high) if low <= high else (high, low)

    def to_dict(self) -> dict:
        return {
            "p0": self.p0.tolist(),
            "yaw": self.yaw,
            "roll": self.roll,
            "pitch": self.pitch,
            "pan_scale": self.pan_scale,
            "pan_zero": self.pan_zero,
            "tilt_scale": self.tilt_scale,
            "tilt_zero": self.tilt_zero,
            "nozzle_offset": self.nozzle_offset,
        }

    @classmethod
    def from_dict(cls, data: dict) -> GimbalParams:
        return cls(
            p0=np.array(data["p0"], dtype=float),
            yaw=float(data["yaw"]),
            roll=float(data["roll"]),
            pitch=float(data["pitch"]),
            pan_scale=float(data["pan_scale"]),
            pan_zero=float(data["pan_zero"]),
            tilt_scale=float(data["tilt_scale"]),
            tilt_zero=float(data["tilt_zero"]),
            nozzle_offset=float(data["nozzle_offset"]),
        )

    @classmethod
    def nominal(cls, p0, yaw: float = 0.0, tilt_zero: float = 4000.0) -> GimbalParams:
        return cls(
            p0=np.array(p0, dtype=float),
            yaw=yaw,
            roll=0.0,
            pitch=0.0,
            pan_scale=NOMINAL_SCALE,
            pan_zero=0.0,
            tilt_scale=NOMINAL_SCALE,
            tilt_zero=tilt_zero,
            nozzle_offset=0.05,
        )


def point_on_ray(params: GimbalParams, pan_cdeg: float, tilt_cdeg: float, distance: float) -> np.ndarray:
    origin, direction = params.ray(pan_cdeg, tilt_cdeg)
    return origin + distance * direction


def ray_residual(params: GimbalParams, pan_cdeg: float, tilt_cdeg: float, point: np.ndarray) -> np.ndarray:
    origin, direction = params.ray(pan_cdeg, tilt_cdeg)
    offset = np.asarray(point, dtype=float) - origin
    helper = np.array([0.0, 0.0, 1.0]) if abs(direction[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    basis = np.cross(direction, helper)
    basis /= np.linalg.norm(basis)
    other = np.cross(direction, basis)
    return np.array([np.dot(offset, basis), np.dot(offset, other)])
