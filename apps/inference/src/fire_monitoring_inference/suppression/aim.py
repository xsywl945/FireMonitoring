from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .ballistics import solve_pitch
from .kinematics import GimbalParams


@dataclass
class AimSolution:
    pan_cdeg: int
    tilt_cdeg: int
    pan_rad: float
    tilt_rad: float
    range_m: float


def _pan_to_target(params: GimbalParams, target: np.ndarray) -> tuple[float, float, float]:
    local = params.base().T @ (np.asarray(target, dtype=float) - params.p0)
    pan = float(np.atan2(local[1], local[0]))
    for _ in range(12):
        origin = np.array(
            [params.nozzle_offset * np.cos(pan), params.nozzle_offset * np.sin(pan), 0.0]
        )
        delta = local - origin
        updated = float(np.atan2(delta[1], delta[0]))
        if abs(updated - pan) < 1e-12:
            pan = updated
            break
        pan = updated
    else:
        delta = local - np.array(
            [params.nozzle_offset * np.cos(pan), params.nozzle_offset * np.sin(pan), 0.0]
        )
    horizontal = float(np.hypot(delta[0], delta[1]))
    return pan, horizontal, float(delta[2])


def solve_aim(params: GimbalParams, target: np.ndarray, speed: float, drag: float) -> AimSolution | None:
    pan, horizontal, height = _pan_to_target(params, np.asarray(target, dtype=float))
    low, high = params.tilt_window()
    tilt = solve_pitch(horizontal, height, speed, drag, low=low, high=high)
    if tilt is None:
        return None
    command = params.command(pan, tilt)
    if command is None:
        return None
    return AimSolution(
        pan_cdeg=command[0],
        tilt_cdeg=command[1],
        pan_rad=pan,
        tilt_rad=tilt,
        range_m=horizontal,
    )
