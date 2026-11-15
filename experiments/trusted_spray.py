from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from experiments.plotting import configure_font, save_figure, write_json
from fire_monitoring_inference.suppression.coverage import pattern_cover_probability
from fire_monitoring_inference.suppression.feedback import plan_path, plan_spray, zigzag

DWELL_S = 1.0
RADIUS_M = 0.2
SIGMAS_M = (0.05, 0.10, 0.20, 0.35, 0.55, 0.80)
DRAWS = 80
COVER_THRESHOLD = 0.5
MAX_POINTS = 3
FIXED_COVARIANCE = np.diag([0.3**2, 0.3**2, 0.02**2])
METHODS = ("fixed_point", "fixed_horizontal", "ellipse", "ellipse_gated")
BASIS = {
    "radius_m": "沿用原先的 0.2 m。配置里的 cover_radius_m 是 1 m，用 1 m 时大协方差也会被一次喷水盖住。",
    "sigmas_m": "定位标准差从小于半径到数倍半径。不是从结果里挑的。",
    "fixed_sweep_sigma_m": "固定水平扫射的水平标准差 0.3 m，不随本次协方差改变。",
    "max_points": "单次喷射 5 s，最多修正 2 次，最多 3 个落点，对应 max_water_s 15。间距等于喷射半径。",
    "cover_threshold": "config.example.json 的 suppression.cover_threshold，0.5。和路径并集覆盖概率比较。",
    "dwell_s": "图上每个落点按 1 s 计，用来比较路径长度。",
}


def _nominal(covariance: np.ndarray, points: list[np.ndarray], radius: float) -> float:
    return pattern_cover_probability(covariance, np.stack(points), radius)


def _patterns(covariance: np.ndarray, radius: float) -> dict:
    estimate = np.zeros(3)
    fixed_h = zigzag(estimate, FIXED_COVARIANCE, radius)
    planned = plan_path(estimate, covariance, radius, max_points=MAX_POINTS)
    gated = plan_spray(
        estimate,
        covariance,
        radius,
        max_points=MAX_POINTS,
        threshold=COVER_THRESHOLD,
    )
    return {
        "fixed_point": {"points": [estimate], "spray": True, "nominal": _nominal(covariance, [estimate], radius)},
        "fixed_horizontal": {
            "points": fixed_h,
            "spray": True,
            "nominal": _nominal(covariance, fixed_h, radius),
        },
        "ellipse": {"points": planned["points"], "spray": True, "nominal": planned["nominal"]},
        "ellipse_gated": gated,
    }


def sweep(draws: int, seed: int, radius: float = RADIUS_M) -> dict:
    if draws < 2:
        raise SystemExit("每个协方差至少抽 2 次")
    rng = np.random.default_rng(seed)
    rows = []
    pairs: dict[str, list[dict]] = {name: [] for name in METHODS}
    for sigma in SIGMAS_M:
        covariance = float(sigma) ** 2 * np.eye(3)
        patterns = _patterns(covariance, radius)
        hits = {name: [] for name in METHODS}
        water = {name: [] for name in METHODS}
        refused = {name: [] for name in METHODS}
        nominal = {name: patterns[name]["nominal"] for name in METHODS}
        for _index in range(draws):
            truth = rng.multivariate_normal(np.zeros(3), covariance)
            for name, plan in patterns.items():
                if not plan["spray"]:
                    hits[name].append(False)
                    water[name].append(0.0)
                    refused[name].append(True)
                    continue
                points = plan["points"]
                hit = any(float(np.linalg.norm(point - truth)) <= radius for point in points)
                hits[name].append(hit)
                water[name].append(len(points) * DWELL_S)
                refused[name].append(False)
                pairs[name].append({"nominal": nominal[name], "hit": hit})
        entry = {"sigma_m": float(sigma)}
        for name in METHODS:
            hit_rate = float(np.mean(hits[name]))
            entry[name] = {
                "hit_rate": hit_rate,
                "hit_rate_std": float(np.sqrt(hit_rate * (1.0 - hit_rate) / draws)),
                "water_s": float(np.mean(water[name])),
                "refusal_rate": float(np.mean(refused[name])),
                "nominal": nominal[name],
                "n": draws,
            }
        rows.append(entry)
    return {
        "data": "合成数据",
        "seed": seed,
        "draws": draws,
        "radius_m": radius,
        "dwell_s": DWELL_S,
        "cover_threshold": COVER_THRESHOLD,
        "max_points": MAX_POINTS,
        "basis": BASIS,
        "sweep": rows,
        "calibration": _bins(pairs),
        "note": "火点相对估计点按给定协方差抽取。拒喷时用水为 0，不计命中。",
    }


def _bins(pairs: dict[str, list[dict]]) -> dict[str, list[dict]]:
    edges = (0.0, 0.2, 0.4, 0.6, 0.8, 1.01)
    result = {}
    for name, rows in pairs.items():
        grouped: dict[str, list[dict]] = {}
        for row in rows:
            for low, high in zip(edges, edges[1:]):
                if low <= row["nominal"] < high:
                    key = f"{low:.1f}-{min(high, 1):.1f}"
                    grouped.setdefault(key, []).append(row)
                    break
        result[name] = [
            {
                "bin": key,
                "n": len(chosen),
                "nominal_mean": float(np.mean([item["nominal"] for item in chosen])),
                "hit_rate": float(np.mean([item["hit"] for item in chosen])),
            }
            for key, chosen in sorted(grouped.items())
        ]
    return result


def _plot(payload: dict, directory: Path) -> None:
    configure_font()
    import matplotlib.pyplot as plt

    labels = {
        "fixed_point": "固定点",
        "fixed_horizontal": "固定水平扫射",
        "ellipse": "协方差二维扫射",
        "ellipse_gated": "二维扫射+拒喷",
    }
    colors = {
        "fixed_point": "#0072B2",
        "fixed_horizontal": "#E69F00",
        "ellipse": "#009E73",
        "ellipse_gated": "#CC79A7",
    }
    rows = payload["sweep"]
    sigmas = [row["sigma_m"] for row in rows]
    fig, axes = plt.subplots(1, 3, figsize=(10.2, 3.5))
    metrics = (
        ("hit_rate", "hit_rate_std", "命中率", (0, 1)),
        ("water_s", None, "用水时长 (s)", None),
        ("refusal_rate", None, "拒喷比例", (0, 1)),
    )
    for axis, (key, err, ylabel, ylim) in zip(axes, metrics, strict=True):
        for name in METHODS:
            y = [row[name][key] for row in rows]
            if err is None:
                axis.plot(sigmas, y, marker="o", color=colors[name], label=labels[name])
            else:
                axis.errorbar(
                    sigmas,
                    y,
                    yerr=[row[name][err] for row in rows],
                    marker="o",
                    capsize=3,
                    color=colors[name],
                    label=labels[name],
                )
        axis.set_xlabel("定位标准差 (m)")
        axis.set_ylabel(ylabel)
        if ylim is not None:
            axis.set_ylim(*ylim)
    axes[0].legend(frameon=False, fontsize=7)
    fig.suptitle("喷射随定位协方差变化（合成数据）")
    fig.tight_layout()
    save_figure(fig, directory, "sigma-sweep")

    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    ax.plot([0, 1], [0, 1], color="#999999", linewidth=1)
    for name, curve in payload["calibration"].items():
        if not curve:
            continue
        ax.plot(
            [row["nominal_mean"] for row in curve],
            [row["hit_rate"] for row in curve],
            marker="o",
            color=colors[name],
            label=labels[name],
        )
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("名义覆盖概率")
    ax.set_ylabel("实测命中率")
    ax.set_title("覆盖概率校准（合成数据）")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    save_figure(fig, directory, "calibration")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="可信喷射随定位协方差变化")
    parser.add_argument("--draws", type=int, default=DRAWS)
    parser.add_argument("--seed", type=int, default=20261115)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = sweep(args.draws, args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    write_json(args.out / "result.json", payload)
    _plot(payload, args.out)


if __name__ == "__main__":
    main()
