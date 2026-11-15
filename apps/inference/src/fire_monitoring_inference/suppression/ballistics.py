from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

G = 9.80665


def _accel(velocity: np.ndarray, drag: float) -> np.ndarray:
    speed = float(np.linalg.norm(velocity))
    return np.array([0.0, -G]) - drag * speed * velocity


def _deriv(state: np.ndarray, drag: float) -> np.ndarray:
    return np.concatenate([state[2:], _accel(state[2:], drag)])


def rk4_step(state: np.ndarray, dt: float, drag: float) -> np.ndarray:
    k1 = _deriv(state, drag)
    k2 = _deriv(state + 0.5 * dt * k1, drag)
    k3 = _deriv(state + 0.5 * dt * k2, drag)
    k4 = _deriv(state + dt * k3, drag)
    return state + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)


def integrate(
    pitch: float,
    speed: float,
    drag: float,
    *,
    dt: float = 0.01,
    t_max: float = 6.0,
    max_range: float | None = None,
) -> np.ndarray:
    velocity = speed * np.array([np.cos(pitch), np.sin(pitch)])
    state = np.array([0.0, 0.0, velocity[0], velocity[1]])
    rows = [state.copy()]
    elapsed = 0.0
    while elapsed < t_max:
        state = rk4_step(state, dt, drag)
        rows.append(state.copy())
        elapsed += dt
        if max_range is not None and state[0] >= max_range:
            break
        if state[2] <= 0 and elapsed > 0.05:
            break
    return np.vstack(rows)


def height_at_range(samples: np.ndarray, target_range: float) -> float | None:
    downrange = samples[:, 0]
    if target_range < 0 or downrange[-1] < target_range:
        return None
    index = int(np.searchsorted(downrange, target_range))
    if index == 0:
        return float(samples[0, 1])
    span = downrange[index] - downrange[index - 1]
    if span <= 0:
        return None
    weight = (target_range - downrange[index - 1]) / span
    return float(samples[index - 1, 1] + weight * (samples[index, 1] - samples[index - 1, 1]))


def landing_range(pitch: float, speed: float, drag: float) -> float:
    samples = integrate(pitch, speed, drag)
    height = samples[:, 1]
    crossed = np.where((height[:-1] > 0) & (height[1:] <= 0))[0]
    if len(crossed) == 0:
        raise RuntimeError("trajectory did not return to the muzzle height")
    index = int(crossed[0])
    span = height[index] - height[index + 1]
    weight = height[index] / span
    return float(samples[index, 0] + weight * (samples[index + 1, 0] - samples[index, 0]))


def solve_pitch(
    target_range: float,
    target_height: float,
    speed: float,
    drag: float,
    *,
    low: float,
    high: float,
) -> float | None:
    if target_range <= 0.05 or high <= low:
        return None
    grid = np.linspace(low, high, 31)

    def error(pitch: float) -> float | None:
        reached = height_at_range(
            integrate(pitch, speed, drag, max_range=target_range), target_range
        )
        if reached is None:
            return None
        return reached - target_height

    values = [error(float(pitch)) for pitch in grid]
    for index in range(len(grid) - 1):
        left, right = values[index], values[index + 1]
        if left is None or right is None or left == 0 or left * right > 0:
            if left == 0:
                return float(grid[index])
            continue
        lo, hi = float(grid[index]), float(grid[index + 1])
        flo, fhi = left, right
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            fmid = error(mid)
            if fmid is None:
                return None
            if abs(fmid) < 1e-6 or hi - lo < 1e-7:
                return mid
            if flo * fmid <= 0:
                hi, fhi = mid, fmid
            else:
                lo, flo = mid, fmid
        return 0.5 * (lo + hi)
    return None


@dataclass
class DragFit:
    speed: float
    drag: float


def fit_drag(shots: list[tuple[float, float]], *, speed0: float = 10.0, drag0: float = 0.1) -> DragFit:
    pitches = np.array([item[0] for item in shots], dtype=float)
    ranges = np.array([item[1] for item in shots], dtype=float)

    def residual(variables: np.ndarray) -> np.ndarray:
        speed, drag = float(variables[0]), float(variables[1])
        predicted = np.array([landing_range(float(pitch), speed, drag) for pitch in pitches])
        return predicted - ranges

    fitted = least_squares(residual, np.array([speed0, drag0]), bounds=([1.0, 0.0], [40.0, 2.0]))
    if not fitted.success:
        raise RuntimeError(fitted.message)
    return DragFit(speed=float(fitted.x[0]), drag=float(fitted.x[1]))
