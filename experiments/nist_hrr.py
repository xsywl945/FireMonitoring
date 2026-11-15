from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

from experiments.plotting import configure_font, require_file, save_figure, write_json
from fire_monitoring_inference.analysis.growth import fit_heat_release
from fire_monitoring_inference.analysis.size import flame_length_m, heat_release_kw

THRESHOLDS_KW = (100, 500)


def read_hrr(path: Path) -> tuple[np.ndarray, np.ndarray]:
    require_file(path)
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise SystemExit(f"{path} 没有表头")
        fields = set(reader.fieldnames)
        if {"Time (s)", "Heat Release Rate (kW)"} <= fields:
            time_key, hrr_key = "Time (s)", "Heat Release Rate (kW)"
        elif {"time_s", "hrr_kw"} <= fields:
            time_key, hrr_key = "time_s", "hrr_kw"
        else:
            raise SystemExit("热释放 CSV 需要 Time (s),Heat Release Rate (kW) 或 time_s,hrr_kw")
        times, values = [], []
        for row in reader:
            times.append(float(row[time_key]))
            values.append(float(row[hrr_key]))
    if len(times) < 2:
        raise SystemExit(f"{path} 的数据行不足")
    order = np.argsort(times)
    times = np.asarray(times, dtype=float)[order]
    values = np.asarray(values, dtype=float)[order]
    if np.any(np.diff(times) <= 0):
        raise SystemExit("热释放时间不是严格递增")
    return times, values


def read_flames(path: Path, diameter_m: float | None) -> list[dict]:
    require_file(path)
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or "time_s" not in reader.fieldnames or "height_m" not in reader.fieldnames:
            raise SystemExit("火焰序列表头必须包含 time_s,height_m")
        has_diameter = "diameter_m" in reader.fieldnames
        if not has_diameter and diameter_m is None:
            raise SystemExit("火焰序列没有 diameter_m，需要 --diameter-m")
        rows = []
        for row in reader:
            diameter = float(row["diameter_m"]) if has_diameter else float(diameter_m)
            rows.append(
                {"time_s": float(row["time_s"]), "height_m": float(row["height_m"]), "diameter_m": diameter}
            )
    if len(rows) < 2:
        raise SystemExit(f"{path} 的火焰行不足")
    return rows


def _interpolate(times: np.ndarray, values: np.ndarray, moment: float) -> float:
    if moment < times[0] or moment > times[-1]:
        raise SystemExit(f"火焰时间 {moment} 不在热释放时间范围内")
    index = int(np.searchsorted(times, moment))
    if index == 0:
        return float(values[0])
    span = times[index] - times[index - 1]
    weight = (moment - times[index - 1]) / span
    return float(values[index - 1] + weight * (values[index] - values[index - 1]))


def select_window(samples: list[tuple[float, float]]) -> list[tuple[float, float]]:
    ordered = sorted(samples, key=lambda item: item[0])
    best: list[tuple[float, float]] | None = None
    best_slope = 0.0
    for end in {item[0] for item in ordered}:
        selected = [item for item in ordered if end - 20 <= item[0] <= end and item[1] > 0]
        if len(selected) < 2:
            continue
        span = selected[-1][0] - selected[0][0]
        if span < 10 or span > 30:
            continue
        times = np.array([item[0] for item in selected], dtype=float)
        values = np.sqrt(np.array([item[1] for item in selected], dtype=float))
        slope = float(np.polyfit(times, values, 1)[0])
        if slope > max(best_slope, 1e-4):
            best_slope = slope
            best = selected
    if best is None:
        raise ValueError("heat release is not growing")
    return best


def _crossing(times: np.ndarray, values: np.ndarray, level: float) -> float | None:
    indices = np.where(values >= level)[0]
    if len(indices) == 0:
        return None
    return float(times[int(indices[0])])


def evaluate(times: np.ndarray, measured: np.ndarray, flames: list[dict]) -> dict:
    paired = []
    for flame in flames:
        truth = _interpolate(times, measured, flame["time_s"])
        estimate = heat_release_kw(flame["height_m"], flame["diameter_m"])
        paired.append((flame["time_s"], truth, estimate, flame["height_m"]))
    usable = [item for item in paired if item[1] > 1]
    if not usable:
        raise SystemExit("没有大于 1 kW 的对照样本")
    relative = [abs(est - truth) / truth for _, truth, est, _ in usable]
    measured_window = select_window([(item[0], item[1]) for item in paired])
    estimated_window = []
    lookup = {item[0]: item[2] for item in paired}
    for moment, _truth in measured_window:
        if moment not in lookup:
            raise SystemExit(f"增长窗口 {moment} 没有对应的火焰估计")
        estimated_window.append((moment, lookup[moment]))
    measured_fit = fit_heat_release(measured_window)
    estimated_fit = fit_heat_release(estimated_window)
    thresholds = []
    for level in THRESHOLDS_KW:
        actual = _crossing(times, measured, level)
        predicted = estimated_fit["t0"] + (level / estimated_fit["alpha"]) ** 0.5
        thresholds.append(
            {
                "level_kw": level,
                "predicted_s": predicted,
                "actual_s": actual,
                "error_s": None if actual is None else predicted - actual,
                "reached": actual is not None,
            }
        )
    return {
        "relative_error": {
            "n": len(relative),
            "mean": float(np.mean(relative)),
            "p90": float(np.quantile(relative, 0.9)),
            "max": float(np.max(relative)),
        },
        "growth": {
            "measured_bin": measured_fit["bin"],
            "estimated_bin": estimated_fit["bin"],
            "correct": measured_fit["bin"] == estimated_fit["bin"],
            "measured_alpha": measured_fit["alpha"],
            "estimated_alpha": estimated_fit["alpha"],
        },
        "thresholds": thresholds,
        "series": [
            {"t_s": item[0], "measured_kw": item[1], "estimated_kw": item[2]} for item in paired
        ],
    }


def synthetic_inputs(seed: int = 20261115) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    del seed
    alpha = 0.1876
    diameter = 0.4
    times = np.arange(0, 41, dtype=float)
    measured = alpha * times**2
    flames = []
    for moment, heat in zip(times, measured, strict=True):
        if heat <= 1:
            continue
        height = flame_length_m(float(heat), diameter)
        if height <= 0:
            continue
        flames.append({"time_s": float(moment), "height_m": float(height), "diameter_m": diameter})
    return times, measured, flames


def measure_frame(frame, px_per_m: float) -> float:
    import cv2

    if px_per_m <= 0:
        raise SystemExit("px_per_m 必须为正")
    value = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)[:, :, 2]
    rows = np.where((value >= 200).any(axis=1))[0]
    if len(rows) == 0:
        raise SystemExit("画面里没有亮区，无法量火焰高度")
    return float(rows.max() - rows.min() + 1) / px_per_m


def heights_from_video(path: Path, px_per_m: float, diameter_m: float) -> list[dict]:
    import cv2

    require_file(path)
    capture = cv2.VideoCapture(str(path))
    fps = capture.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        capture.release()
        raise SystemExit("视频没有帧率")
    rows = []
    index = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        rows.append(
            {
                "time_s": index / fps,
                "height_m": measure_frame(frame, px_per_m),
                "diameter_m": diameter_m,
            }
        )
        index += 1
    capture.release()
    if len(rows) < 2:
        raise SystemExit("视频帧数不足")
    return rows


def _plot(result: dict, directory: Path, title: str) -> None:
    configure_font()
    import matplotlib.pyplot as plt

    series = result["series"]
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    ax.plot([item["t_s"] for item in series], [item["measured_kw"] for item in series], label="测量", color="#0072B2")
    ax.plot(
        [item["t_s"] for item in series],
        [item["estimated_kw"] for item in series],
        label="Heskestad",
        color="#D55E00",
    )
    ax.set_xlabel("时间 (s)")
    ax.set_ylabel("热释放速率 (kW)")
    ax.set_title(title)
    ax.legend(frameon=False)
    fig.tight_layout()
    save_figure(fig, directory, "hrr")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="用 Heskestad 和 t² 对照热释放速率")
    parser.add_argument("--hrr", type=Path)
    parser.add_argument("--flames", type=Path)
    parser.add_argument("--video", type=Path)
    parser.add_argument("--px-per-m", type=float)
    parser.add_argument("--diameter-m", type=float)
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.synthetic:
        times, measured, flames = synthetic_inputs()
        data = "合成数据"
        source = "t² 反算的火焰高度"
    else:
        if args.hrr is None:
            raise SystemExit("需要 --hrr，或改用 --synthetic")
        times, measured = read_hrr(args.hrr)
        if args.flames:
            flames = read_flames(args.flames, args.diameter_m)
        elif args.video:
            if args.px_per_m is None or args.diameter_m is None:
                raise SystemExit("从视频量火焰需要 --px-per-m 和 --diameter-m")
            flames = heights_from_video(args.video, args.px_per_m, args.diameter_m)
        else:
            raise SystemExit("需要 --flames 或 --video")
        data = "测量输入"
        source = str(args.hrr)
    result = evaluate(times, measured, flames)
    result["growth"]["accuracy"] = 1.0 if result["growth"]["correct"] else 0.0
    payload = {"data": data, "source": source, **result}
    args.out.mkdir(parents=True, exist_ok=True)
    stored = {key: value for key, value in payload.items() if key != "series"}
    stored["series_n"] = len(result["series"])
    write_json(args.out / "result.json", stored)
    title = "热释放速率（合成数据）" if data == "合成数据" else "热释放速率"
    _plot(result, args.out, title)


if __name__ == "__main__":
    main()
