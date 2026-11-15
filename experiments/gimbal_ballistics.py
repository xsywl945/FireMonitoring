from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from experiments.plotting import configure_font, require_file, save_figure, write_json
from fire_monitoring_inference.suppression.aim import _pan_to_target, solve_aim
from fire_monitoring_inference.suppression.ballistics import height_at_range, integrate
from fire_monitoring_inference.suppression.calibrate import LaserSample, fit_gimbal
from fire_monitoring_inference.suppression.kinematics import NOMINAL_SCALE, GimbalParams, point_on_ray

METHODS = ("manual", "self_cal", "ballistic")
METHOD_LABEL = {"manual": "人工位姿", "self_cal": "激光自标定", "ballistic": "弹道补偿"}


def _miss(truth: GimbalParams, pan: int, tilt: int, target: np.ndarray, speed: float, drag: float) -> float:
    origin, direction = truth.ray(pan, tilt)
    pitch = float(np.asin(np.clip(direction[2], -1.0, 1.0)))
    azimuth = float(np.atan2(direction[1], direction[0]))
    relative = np.asarray(target, dtype=float) - origin
    downrange = float(relative[0] * np.cos(azimuth) + relative[1] * np.sin(azimuth))
    cross = float(-relative[0] * np.sin(azimuth) + relative[1] * np.cos(azimuth))
    if downrange <= 0:
        return float(np.linalg.norm(relative))
    samples = integrate(pitch, speed, drag, max_range=downrange)
    height = height_at_range(samples, downrange)
    if height is None:
        end = samples[-1]
        landed = origin + np.array(
            [end[0] * np.cos(azimuth), end[0] * np.sin(azimuth), end[1]]
        )
        return float(np.linalg.norm(landed - target))
    return float(np.hypot(cross, height - relative[2]))


def _geometric(params: GimbalParams, target: np.ndarray) -> tuple[int, int]:
    pan, horizontal, height = _pan_to_target(params, np.asarray(target, dtype=float))
    tilt = float(np.atan2(height, horizontal))
    command = params.command(pan, tilt)
    if command is None:
        raise RuntimeError("几何瞄准超出云台行程")
    return command


def _ballistic(params: GimbalParams, target: np.ndarray, speed: float, drag: float) -> tuple[int, int]:
    aim = solve_aim(params, np.asarray(target, dtype=float), speed, drag)
    if aim is None:
        raise RuntimeError("弹道瞄准无解")
    return aim.pan_cdeg, aim.tilt_cdeg


def _mean(values: list[float]) -> float:
    if not values:
        raise SystemExit("没有命中误差样本")
    return float(np.mean(values))


def score_landings(rows: list[dict]) -> dict[str, float]:
    grouped: dict[str, list[float]] = {name: [] for name in METHODS}
    for row in rows:
        method = row["method"]
        if method not in grouped:
            raise SystemExit(f"未知瞄准方式 {method}")
        target = np.array([row["x_m"], row["y_m"], row["z_m"]], dtype=float)
        landing = np.array(
            [row["landing_x_m"], row["landing_y_m"], row["landing_z_m"]], dtype=float
        )
        grouped[method].append(float(np.linalg.norm(landing - target)))
    missing = [name for name, values in grouped.items() if not values]
    if missing:
        raise SystemExit("落点 CSV 缺少方式：" + "、".join(missing))
    return {name: _mean(values) for name, values in grouped.items()}


def _take(samples: list[LaserSample], count: int) -> list[LaserSample]:
    if count > len(samples):
        raise SystemExit(f"角度组数 {count} 超过样本 {len(samples)}")
    index = np.unique(np.round(np.linspace(0, len(samples) - 1, count)).astype(int))
    if len(index) != count:
        raise RuntimeError("角度组抽样出现重复")
    return [samples[int(item)] for item in index]


def residual_curve(samples: list[LaserSample], initial: GimbalParams, counts: list[int]) -> list[dict]:
    if len(samples) < 12:
        raise SystemExit("激光样本至少 12 组")
    rows = []
    for count in counts:
        chosen = _take(samples, count)
        fitted = fit_gimbal(chosen, initial)
        rows.append(
            {
                "groups": count,
                "mean_residual_m": float(np.mean(fitted.residuals_m)),
                "max_residual_m": float(np.max(fitted.residuals_m)),
            }
        )
    return rows


def _truth_and_manual() -> tuple[GimbalParams, GimbalParams]:
    truth = GimbalParams(
        p0=np.array([0.0, 0.0, 2.2]),
        yaw=0.0,
        roll=0.0,
        pitch=0.0,
        pan_scale=NOMINAL_SCALE,
        pan_zero=0.0,
        tilt_scale=NOMINAL_SCALE,
        tilt_zero=4000.0,
        nozzle_offset=0.12,
    )
    manual = GimbalParams(
        p0=np.array([0.18, -0.12, 2.02]),
        yaw=float(np.deg2rad(8.0)),
        roll=float(np.deg2rad(2.0)),
        pitch=float(np.deg2rad(-1.5)),
        pan_scale=NOMINAL_SCALE,
        pan_zero=0.0,
        tilt_scale=NOMINAL_SCALE,
        tilt_zero=4180.0,
        nozzle_offset=0.05,
    )
    return truth, manual


def _laser_samples(truth: GimbalParams, seed: int) -> list[LaserSample]:
    rng = np.random.default_rng(seed)
    poses = [
        (pan, tilt)
        for pan in (-8000, -5000, -2000, 1000, 4000, 7000)
        for tilt in (600, 1400, 2200, 3000, 3800, 4600)
    ]
    samples = []
    for index, (pan, tilt) in enumerate(poses):
        distance = 2.4 + (index % 5) * 0.55
        xyz = point_on_ray(truth, pan, tilt, distance) + rng.normal(0, 0.002, 3)
        samples.append(LaserSample(pan, tilt, xyz))
    return samples


def _targets() -> list[np.ndarray]:
    return [
        np.array([2.6, 0.3, 1.15]),
        np.array([3.4, -0.5, 1.05]),
        np.array([4.2, 0.6, 0.95]),
        np.array([3.0, 1.0, 1.2]),
    ]


def _hit_errors(
    truth: GimbalParams,
    manual: GimbalParams,
    fitted: GimbalParams,
    targets: list[np.ndarray],
    speed: float,
    drag: float,
) -> dict[str, float]:
    grouped = {name: [] for name in METHODS}
    for target in targets:
        commands = {
            "manual": _geometric(manual, target),
            "self_cal": _geometric(fitted, target),
            "ballistic": _ballistic(fitted, target, speed, drag),
        }
        for name, command in commands.items():
            grouped[name].append(_miss(truth, command[0], command[1], target, speed, drag))
    return {name: _mean(values) for name, values in grouped.items()}


def synthetic_case(seed: int = 20261115) -> dict:
    truth, manual = _truth_and_manual()
    samples = _laser_samples(truth, seed)
    speed, drag = 10.0, 0.08
    fitted = fit_gimbal(samples, manual).params
    targets = _targets()
    hits = _hit_errors(truth, manual, fitted, targets, speed, drag)
    counts = [12, 18, 24, 36]
    curve = []
    for count in counts:
        partial = fit_gimbal(_take(samples, count), manual).params
        errors = _hit_errors(truth, manual, partial, targets, speed, drag)
        curve.append({"groups": count, "hit_error_m": errors["ballistic"]})
    return {
        "data": "合成数据",
        "seed": seed,
        "speed_m_s": speed,
        "drag": drag,
        "hit_error_m": hits,
        "convergence": curve,
        "note": "命中误差是按真实云台和弹道积分后，弹着点到目标点的距离。",
    }


def _read_landings(path: Path) -> list[dict]:
    require_file(path)
    fields = ("method", "x_m", "y_m", "z_m", "landing_x_m", "landing_y_m", "landing_z_m")
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or tuple(reader.fieldnames) != fields:
            raise SystemExit(f"落点 CSV 表头必须是：{','.join(fields)}")
        rows = []
        for row in reader:
            item = {"method": row["method"]}
            for name in fields[1:]:
                item[name] = float(row[name])
            rows.append(item)
    if not rows:
        raise SystemExit(f"{path} 没有数据行")
    return rows


def _read_laser(path: Path) -> list[LaserSample]:
    require_file(path)
    fields = ("pan_cdeg", "tilt_cdeg", "x_m", "y_m", "z_m")
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or tuple(reader.fieldnames) != fields:
            raise SystemExit(f"激光 CSV 表头必须是：{','.join(fields)}")
        samples = [
            LaserSample(
                float(row["pan_cdeg"]),
                float(row["tilt_cdeg"]),
                np.array([float(row["x_m"]), float(row["y_m"]), float(row["z_m"])]),
            )
            for row in reader
        ]
    if len(samples) < 12:
        raise SystemExit("激光样本至少 12 组")
    return samples


def _read_manual(path: Path) -> GimbalParams:
    require_file(path)
    return GimbalParams.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _plot_hits(hits: dict[str, float], directory: Path, title: str) -> None:
    configure_font()
    import matplotlib.pyplot as plt

    labels = [METHOD_LABEL[name] for name in METHODS]
    values = [hits[name] for name in METHODS]
    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    ax.bar(labels, values, color=["#D55E00", "#E69F00", "#009E73"])
    ax.set_ylabel("命中误差 (m)")
    ax.set_title(title)
    fig.tight_layout()
    save_figure(fig, directory, "hit-error")


def _plot_curve(rows: list[dict], directory: Path, title: str, ylabel: str, key: str) -> None:
    configure_font()
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    ax.plot([row["groups"] for row in rows], [row[key] for row in rows], marker="o", color="#0072B2")
    ax.set_xlabel("角度组数")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    fig.tight_layout()
    save_figure(fig, directory, "convergence")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="云台自标定与弹道补偿")
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--seed", type=int, default=20261115)
    parser.add_argument("--landings", type=Path)
    parser.add_argument("--laser", type=Path)
    parser.add_argument("--manual", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    field = args.landings or args.laser or args.manual
    if args.synthetic and field:
        raise SystemExit("--synthetic 不和实测 CSV 一起用")
    if not args.synthetic and not (args.landings and args.laser and args.manual):
        raise SystemExit("实测需要同时给出 --landings、--laser 和 --manual，或改用 --synthetic")
    if args.synthetic:
        payload = synthetic_case(args.seed)
        args.out.mkdir(parents=True, exist_ok=True)
        write_json(args.out / "result.json", payload)
        _plot_hits(payload["hit_error_m"], args.out, "命中误差（合成数据）")
        _plot_curve(
            payload["convergence"],
            args.out,
            "自标定组数与命中误差（合成数据）",
            "弹道补偿后的命中误差 (m)",
            "hit_error_m",
        )
        return
    samples = _read_laser(args.laser)
    counts = sorted({count for count in (12, 18, 24, 36, len(samples)) if 12 <= count <= len(samples)})
    hits = score_landings(_read_landings(args.landings))
    curve = residual_curve(samples, _read_manual(args.manual), counts)
    payload = {
        "data": "测量输入",
        "source_landings": str(args.landings),
        "source_laser": str(args.laser),
        "hit_error_m": hits,
        "convergence": curve,
        "note": "实测收敛曲线是激光残差，不是弹着点误差。",
    }
    args.out.mkdir(parents=True, exist_ok=True)
    write_json(args.out / "result.json", payload)
    _plot_hits(hits, args.out, "命中误差")
    _plot_curve(curve, args.out, "自标定组数与激光残差", "平均残差 (m)", "mean_residual_m")


if __name__ == "__main__":
    main()
