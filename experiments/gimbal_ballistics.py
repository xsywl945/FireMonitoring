from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from experiments.plotting import configure_font, require_file, save_figure, write_json
from fire_monitoring_inference.suppression.aim import solve_aim
from fire_monitoring_inference.suppression.ballistics import (
    fit_drag,
    height_at_range,
    integrate,
    landing_range,
)
from fire_monitoring_inference.suppression.calibrate import LaserSample, fit_gimbal
from fire_monitoring_inference.suppression.kinematics import NOMINAL_SCALE, GimbalParams, point_on_ray

METHODS = ("manual", "self_cal", "fitted")
METHOD_LABEL = {
    "manual": "人工+名义弹道",
    "self_cal": "自标定+名义弹道",
    "fitted": "自标定+试喷弹道",
}


@dataclass(frozen=True)
class SyntheticConfig:
    seeds: int = 8
    base_seed: int = 20261115
    manual_position_sigma_m: float = 0.015
    manual_angle_sigma_deg: float = 1.0
    triangulation_sigma_m: float = 0.016
    servo_step_deg: float = 0.01
    backlash_deg: float = 0.2
    nominal_speed_m_s: float = 10.0
    nominal_drag: float = 0.05
    truth_speed_m_s: float = 10.0
    truth_drag: float = 0.10
    speed_jitter_std: float = 0.025
    breakup_sigma_m: float = 0.02
    trial_pitches_deg: tuple[float, ...] = (12.0, 20.0, 28.0, 36.0)
    convergence_groups: tuple[int, ...] = (12, 18, 24, 36)


BASIS = {
    "manual_position_sigma_m": "标准差 0.015 m，约 95% 落在 ±3 cm。按卷尺量云台安装点的误差。",
    "manual_angle_sigma_deg": "标准差 1°，约 95% 落在 ±2°。按量角器量安装角的误差，加在 yaw、roll、pitch 上。",
    "triangulation_sigma_m": "landmark_sigma_px 为 2，演示相机焦距 430 px，约 3.5 m 处横向标准差 2/430×3.5≈0.016 m。",
    "servo_step_deg": "kinematics.NOMINAL_SCALE 是 0.01°，命令按这个步距取整。",
    "backlash_deg": "协议没有回差。按小型云台齿轮间隙取 ±0.2°，没有按图调整。",
    "nominal_speed_m_s": "config.example.json 的 suppression.speed。",
    "nominal_drag": "config.example.json 的 suppression.drag，未辨识的名义值。",
    "truth_drag": "生成用名义阻力的 2 倍。0.05 不是测量值，用来表示名义模型和出水不一致。",
    "speed_jitter_std": "仓库没有压力记录。压力脉动约 5% 时，速度按平方根变化，相对标准差约 2.5%。",
    "breakup_sigma_m": "二次阻力模型没有射流破碎。落点横侧和竖直各加 0.02 m 的零均值噪声，仓库里没有射流宽度。",
}


def _stats(values: list[float]) -> dict:
    if not values:
        raise SystemExit("没有命中误差样本")
    array = np.asarray(values, dtype=float)
    return {
        "n": int(array.size),
        "mean_m": float(np.mean(array)),
        "std_m": float(np.std(array, ddof=1)) if array.size > 1 else 0.0,
        "p90_m": float(np.quantile(array, 0.9)),
        "max_m": float(np.max(array)),
    }


def _mean(values: list[float]) -> float:
    return _stats(values)["mean_m"]


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


def _targets() -> list[np.ndarray]:
    return [
        np.array([2.6, 0.3, 1.15]),
        np.array([3.4, -0.5, 1.05]),
        np.array([4.2, 0.6, 0.95]),
        np.array([3.0, 1.0, 1.2]),
    ]


def _pose_grid() -> list[tuple[int, int]]:
    return [
        (pan, tilt)
        for pan in (-8000, -5000, -2000, 1000, 4000, 7000)
        for tilt in (600, 1400, 2200, 3000, 3800, 4600)
    ]


def _perturb(truth: GimbalParams, rng: np.random.Generator, cfg: SyntheticConfig) -> GimbalParams:
    angle = np.deg2rad(cfg.manual_angle_sigma_deg)
    return GimbalParams(
        p0=truth.p0 + rng.normal(0, cfg.manual_position_sigma_m, 3),
        yaw=truth.yaw + float(rng.normal(0, angle)),
        roll=truth.roll + float(rng.normal(0, angle)),
        pitch=truth.pitch + float(rng.normal(0, angle)),
        pan_scale=truth.pan_scale,
        pan_zero=truth.pan_zero,
        tilt_scale=truth.tilt_scale,
        tilt_zero=truth.tilt_zero,
        nozzle_offset=truth.nozzle_offset,
    )


def _servo(
    params: GimbalParams,
    pan_cdeg: int,
    tilt_cdeg: int,
    rng: np.random.Generator,
    cfg: SyntheticConfig,
) -> tuple[int, int]:
    backlash = np.deg2rad(cfg.backlash_deg)
    pan_rad = params.pan_scale * (pan_cdeg - params.pan_zero) + float(rng.uniform(-backlash, backlash))
    tilt_rad = params.tilt_scale * (tilt_cdeg - params.tilt_zero) + float(rng.uniform(-backlash, backlash))
    pan = int(round(pan_rad / params.pan_scale + params.pan_zero))
    tilt = int(round(tilt_rad / params.tilt_scale + params.tilt_zero))
    return pan, tilt


def _laser(truth: GimbalParams, rng: np.random.Generator, cfg: SyntheticConfig) -> list[LaserSample]:
    samples = []
    for index, (pan, tilt) in enumerate(_pose_grid()):
        achieved_pan, achieved_tilt = _servo(truth, pan, tilt, rng, cfg)
        distance = 2.4 + (index % 5) * 0.55
        xyz = point_on_ray(truth, achieved_pan, achieved_tilt, distance)
        xyz = xyz + rng.normal(0, cfg.triangulation_sigma_m, 3)
        samples.append(LaserSample(pan, tilt, xyz))
    return samples


def _aim(params: GimbalParams, target: np.ndarray, speed: float, drag: float) -> tuple[int, int]:
    solved = solve_aim(params, np.asarray(target, dtype=float), speed, drag)
    if solved is None:
        raise RuntimeError("弹道瞄准无解")
    return solved.pan_cdeg, solved.tilt_cdeg


def _fly(
    truth: GimbalParams,
    pan: int,
    tilt: int,
    target: np.ndarray,
    speed: float,
    drag: float,
    rng: np.random.Generator,
    breakup_sigma_m: float,
) -> float:
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
        landed = origin + np.array([end[0] * np.cos(azimuth), end[0] * np.sin(azimuth), end[1]])
        return float(np.linalg.norm(landed - target))
    water_cross = float(rng.normal(0, breakup_sigma_m))
    water_height = height + float(rng.normal(0, breakup_sigma_m))
    return float(np.hypot(cross - water_cross, water_height - relative[2]))


def _shot(
    truth: GimbalParams,
    params: GimbalParams,
    target: np.ndarray,
    aim_speed: float,
    aim_drag: float,
    rng: np.random.Generator,
    cfg: SyntheticConfig,
) -> float:
    pan, tilt = _aim(params, target, aim_speed, aim_drag)
    pan, tilt = _servo(truth, pan, tilt, rng, cfg)
    speed = cfg.truth_speed_m_s * (1.0 + float(rng.normal(0, cfg.speed_jitter_std)))
    return _fly(truth, pan, tilt, target, speed, cfg.truth_drag, rng, cfg.breakup_sigma_m)


def _fit_trials(rng: np.random.Generator, cfg: SyntheticConfig):
    measured_sigma = float(np.hypot(cfg.triangulation_sigma_m, cfg.breakup_sigma_m))
    shots = []
    for pitch_deg in cfg.trial_pitches_deg:
        pitch = float(np.deg2rad(pitch_deg))
        speed = cfg.truth_speed_m_s * (1.0 + float(rng.normal(0, cfg.speed_jitter_std)))
        distance = landing_range(pitch, speed, cfg.truth_drag)
        shots.append((pitch, distance + float(rng.normal(0, measured_sigma))))
    return fit_drag(shots, speed0=cfg.nominal_speed_m_s, drag0=cfg.nominal_drag)


def _one_seed(seed: int, cfg: SyntheticConfig) -> dict:
    rng = np.random.default_rng(seed)
    truth = GimbalParams.nominal([0.0, 0.0, 2.2])
    if not np.isclose(truth.pan_scale, NOMINAL_SCALE):
        raise RuntimeError("云台步距和 NOMINAL_SCALE 不一致")
    manual = _perturb(truth, rng, cfg)
    samples = _laser(truth, rng, cfg)
    calibrated = fit_gimbal(samples, manual).params
    drag = _fit_trials(rng, cfg)
    targets = _targets()
    grouped = {name: [] for name in METHODS}
    for target in targets:
        grouped["manual"].append(
            _shot(truth, manual, target, cfg.nominal_speed_m_s, cfg.nominal_drag, rng, cfg)
        )
        grouped["self_cal"].append(
            _shot(truth, calibrated, target, cfg.nominal_speed_m_s, cfg.nominal_drag, rng, cfg)
        )
        grouped["fitted"].append(_shot(truth, calibrated, target, drag.speed, drag.drag, rng, cfg))
    curve = {}
    for count in cfg.convergence_groups:
        pose = fit_gimbal(_take(samples, count), manual).params
        misses = [
            _shot(truth, pose, target, drag.speed, drag.drag, rng, cfg) for target in targets
        ]
        curve[count] = float(np.mean(misses))
    return {
        "seed": seed,
        "mean_m": {name: float(np.mean(values)) for name, values in grouped.items()},
        "fitted_speed_m_s": drag.speed,
        "fitted_drag": drag.drag,
        "curve": curve,
    }


def synthetic_case(cfg: SyntheticConfig | None = None) -> dict:
    cfg = cfg or SyntheticConfig()
    if cfg.seeds < 2:
        raise SystemExit("至少两个随机种子才能算 P90 和误差棒")
    if cfg.truth_drag == cfg.nominal_drag and cfg.breakup_sigma_m == 0 and cfg.speed_jitter_std == 0:
        raise SystemExit("生成模型和反解模型不能设成同一个无噪声模型")
    rows = [_one_seed(cfg.base_seed + index, cfg) for index in range(cfg.seeds)]
    hit_error = {
        name: _stats([row["mean_m"][name] for row in rows]) for name in METHODS
    }
    convergence = []
    for count in cfg.convergence_groups:
        convergence.append({"groups": count, **_stats([row["curve"][count] for row in rows])})
    return {
        "data": "合成数据",
        "config": asdict(cfg),
        "basis": BASIS,
        "definitions": {
            "manual": "人工卷尺位姿（含测量噪声）加名义弹道",
            "self_cal": "激光自标定位姿加名义弹道",
            "fitted": "激光自标定位姿加试喷拟合弹道",
        },
        "hit_error_m": hit_error,
        "convergence": convergence,
        "seeds": rows,
        "note": (
            "生成用带阻力的 integrate，并加上速度抖动和射流破碎。"
            "反解用 solve_aim。名义组用配置里的 speed 和 drag，试喷组用 fit_drag。"
            "上一版自标定更差，是因为那两组都按视线瞄准，重力落差主导了脱靶。"
        ),
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


def _plot_hits(hits: dict[str, dict], directory: Path, title: str) -> None:
    configure_font()
    import matplotlib.pyplot as plt

    labels = [METHOD_LABEL[name] for name in METHODS]
    means = [hits[name]["mean_m"] for name in METHODS]
    stds = [hits[name]["std_m"] for name in METHODS]
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    ax.bar(labels, means, yerr=stds, capsize=4, color=["#D55E00", "#E69F00", "#009E73"])
    ax.set_ylabel("命中误差 (m)")
    ax.set_title(title)
    fig.tight_layout()
    save_figure(fig, directory, "hit-error")


def _plot_curve(rows: list[dict], directory: Path, title: str, ylabel: str) -> None:
    configure_font()
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    ax.errorbar(
        [row["groups"] for row in rows],
        [row["mean_m"] for row in rows],
        yerr=[row["std_m"] for row in rows],
        marker="o",
        capsize=4,
        color="#0072B2",
    )
    ax.set_xlabel("角度组数")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    fig.tight_layout()
    save_figure(fig, directory, "convergence")


def _plot_field_hits(hits: dict[str, float], directory: Path, title: str) -> None:
    configure_font()
    import matplotlib.pyplot as plt

    labels = [METHOD_LABEL[name] for name in METHODS]
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    ax.bar(labels, [hits[name] for name in METHODS], color=["#D55E00", "#E69F00", "#009E73"])
    ax.set_ylabel("命中误差 (m)")
    ax.set_title(title)
    fig.tight_layout()
    save_figure(fig, directory, "hit-error")


def _plot_field_curve(rows: list[dict], directory: Path, title: str) -> None:
    configure_font()
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    ax.plot(
        [row["groups"] for row in rows],
        [row["mean_residual_m"] for row in rows],
        marker="o",
        color="#0072B2",
    )
    ax.set_xlabel("角度组数")
    ax.set_ylabel("平均残差 (m)")
    ax.set_title(title)
    fig.tight_layout()
    save_figure(fig, directory, "convergence")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="云台自标定与弹道补偿")
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--seeds", type=int, default=SyntheticConfig.seeds)
    parser.add_argument("--seed", type=int, default=SyntheticConfig.base_seed)
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
        payload = synthetic_case(SyntheticConfig(seeds=args.seeds, base_seed=args.seed))
        args.out.mkdir(parents=True, exist_ok=True)
        write_json(args.out / "result.json", payload)
        _plot_hits(payload["hit_error_m"], args.out, "命中误差（合成数据）")
        _plot_curve(
            payload["convergence"],
            args.out,
            "自标定组数与命中误差（合成数据）",
            "试喷弹道的命中误差 (m)",
        )
        return
    samples = _read_laser(args.laser)
    counts = sorted(
        {count for count in (12, 18, 24, 36, len(samples)) if 12 <= count <= len(samples)}
    )
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
    _plot_field_hits(hits, args.out, "命中误差")
    _plot_field_curve(curve, args.out, "自标定组数与激光残差")


if __name__ == "__main__":
    main()
