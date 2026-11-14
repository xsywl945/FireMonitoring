from __future__ import annotations

import math

import numpy as np

from .rules import load_rules

BIN_LABEL = {
    "slow": "慢速",
    "medium": "中速",
    "fast": "快速",
    "ultrafast": "超快速",
}


def nearest_bin(alpha: float) -> str:
    if alpha <= 0:
        raise ValueError("growth coefficient must be positive")
    bins = load_rules()["growth_bins"]
    return min(bins, key=lambda name: abs(alpha - bins[name]))


def _window(samples: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(samples) < 2:
        raise ValueError("growth needs at least two samples")
    ordered = sorted(samples, key=lambda item: item[0])
    end = ordered[-1][0]
    selected = [item for item in ordered if end - 30 <= item[0] <= end]
    span = selected[-1][0] - selected[0][0]
    if span < 10 or span > 30:
        raise ValueError("growth window must span 10 to 30 seconds")
    return selected


def fit_heat_release(samples: list[tuple[float, float]]) -> dict:
    selected = _window(samples)
    times = np.array([item[0] for item in selected], dtype=float)
    values = np.array([item[1] for item in selected], dtype=float)
    if np.any(values <= 0):
        raise ValueError("heat release must be positive")
    slope, intercept = np.polyfit(times, np.sqrt(values), 1)
    if slope <= 0:
        raise ValueError("heat release is not growing")
    alpha = float(slope**2)
    t0 = float(-intercept / slope)
    bin_name = nearest_bin(alpha)
    reference = load_rules()["growth_bins"][bin_name]
    last = float(times[-1])
    origin = float(times[0])

    def seconds_until(target: float) -> float:
        return t0 + math.sqrt(target / alpha) - last

    curve = []
    for step in range(21):
        moment = origin + (last - origin) * step / 20
        curve.append({"t": moment - origin, "q": alpha * (moment - t0) ** 2})
    return {
        "mode": "heat_release",
        "bin": bin_name,
        "alpha": alpha,
        "t0": t0,
        "reference_alpha": reference,
        "seconds_to_100kw": seconds_until(100),
        "seconds_to_500kw": seconds_until(500),
        "samples": [{"t": float(t - origin), "q": float(q)} for t, q in selected],
        "curve": curve,
        "reason": f"α={alpha:.5f} kW/s²，最接近{BIN_LABEL[bin_name]} {reference}",
    }


def fit_area(samples: list[tuple[float, float]]) -> dict:
    if len(samples) < 2:
        raise ValueError("area growth needs at least two samples")
    ordered = sorted(samples, key=lambda item: item[0])
    times = np.array([item[0] for item in ordered], dtype=float)
    areas = np.array([item[1] for item in ordered], dtype=float)
    if times[-1] <= times[0]:
        raise ValueError("area samples need a time span")
    if np.any(areas <= 0):
        raise ValueError("box area must be positive")
    origin = float(times[0])
    log_slope = float(np.polyfit(times, np.log(areas), 1)[0])
    area_slope = float(np.polyfit(times, areas, 1)[0])
    result = {
        "mode": "area",
        "area_rate_px2_per_s": area_slope,
        "samples": [{"t": float(t - origin), "area": float(area)} for t, area in ordered],
    }
    if log_slope <= 0:
        result["reason"] = "无火点深度，框面积未增大"
        return result
    doubling = math.log(2) / log_slope
    result["doubling_time_s"] = doubling
    result["reason"] = f"无火点深度，框面积倍增时间 {doubling:.1f} 秒"
    return result
