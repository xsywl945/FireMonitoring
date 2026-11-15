from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from .kinematics import NOMINAL_SCALE, GimbalParams, ray_residual


@dataclass
class LaserSample:
    pan_cdeg: float
    tilt_cdeg: float
    xyz: np.ndarray


@dataclass
class CalibrationFit:
    params: GimbalParams
    residuals_m: list[float]


def _pack(params: GimbalParams) -> np.ndarray:
    return np.array(
        [
            *params.p0,
            params.yaw,
            params.roll,
            params.pitch,
            np.log(params.pan_scale / NOMINAL_SCALE),
            params.pan_zero,
            np.log(params.tilt_scale / NOMINAL_SCALE),
            params.tilt_zero,
            params.nozzle_offset,
        ],
        dtype=float,
    )


def _unpack(values: np.ndarray) -> GimbalParams:
    return GimbalParams(
        p0=values[0:3],
        yaw=float(values[3]),
        roll=float(values[4]),
        pitch=float(values[5]),
        pan_scale=NOMINAL_SCALE * float(np.exp(values[6])),
        pan_zero=float(values[7]),
        tilt_scale=NOMINAL_SCALE * float(np.exp(values[8])),
        tilt_zero=float(values[9]),
        nozzle_offset=float(values[10]),
    )


def fit_gimbal(samples: list[LaserSample], initial: GimbalParams) -> CalibrationFit:
    if len(samples) < 12:
        raise ValueError("laser calibration needs at least 12 poses")
    # Base yaw and the pan zero are an additive gauge. Hold the zero on the
    # caller's initial value so the fit returns the yaw, not an arbitrary split.
    anchor = float(initial.pan_zero)

    def residual(values: np.ndarray) -> np.ndarray:
        params = _unpack(values)
        rows = [
            ray_residual(params, sample.pan_cdeg, sample.tilt_cdeg, sample.xyz) for sample in samples
        ]
        rows.append(np.array([(values[7] - anchor) * 1e-3]))
        return np.concatenate(rows)

    fitted = least_squares(
        residual,
        _pack(initial),
        bounds=(
            np.array([-30, -30, -5, -np.pi, -0.35, -0.35, -0.5, -8000, -0.5, -8000, 0.0]),
            np.array([30, 30, 12, np.pi, 0.35, 0.35, 0.5, 8000, 0.5, 8000, 0.8]),
        ),
    )
    if not fitted.success:
        raise RuntimeError(fitted.message)
    params = _unpack(fitted.x)
    residuals = [
        float(np.linalg.norm(ray_residual(params, sample.pan_cdeg, sample.tilt_cdeg, sample.xyz)))
        for sample in samples
    ]
    return CalibrationFit(params=params, residuals_m=residuals)
