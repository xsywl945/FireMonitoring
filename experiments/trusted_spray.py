from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from experiments.plotting import configure_font, save_figure, write_json
from fire_monitoring_inference.suppression.feedback import zigzag

DWELL_S = 1.0
RADIUS_M = 0.2
SIGMAS_M = (0.05, 0.10, 0.20, 0.35, 0.55, 0.80)
DRAWS = 80
FIXED_COVARIANCE = np.diag([0.3**2, 0.3**2, 0.02**2])
BASIS = {
    "radius_m": "沿用原先的 0.2 m。配置里的 cover_radius_m 是 1 m，用 1 m 时大协方差也会被一次喷水盖住。",
    "sigmas_m": "定位标准差从小于半径到数倍半径。不是从结果里挑的。",
    "fixed_sweep_sigma_m": "固定扫射的水平标准差 0.3 m，不随本次协方差改变。",
    "dwell_s": "每个扫射点喷 1 s。",
}


def _patterns(estimate: np.ndarray, covariance: np.ndarray, radius: float) -> dict[str, list[np.ndarray]]:
    return {
        "fixed_point": [estimate],
        "fixed_sweep": zigzag(estimate, FIXED_COVARIANCE, radius),
        "adaptive_sweep": zigzag(estimate, covariance, radius),
    }


def _hit(points: list[np.ndarray], truth: np.ndarray, radius: float) -> bool:
    return any(float(np.linalg.norm(point - truth)) <= radius for point in points)


def sweep(draws: int, seed: int, radius: float = RADIUS_M) -> dict:
    if draws < 2:
        raise SystemExit("每个协方差至少抽 2 次")
    rng = np.random.default_rng(seed)
    names = ("fixed_point", "fixed_sweep", "adaptive_sweep")
    rows = []
    for sigma in SIGMAS_M:
        covariance = float(sigma) ** 2 * np.eye(3)
        hits = {name: [] for name in names}
        water = {name: [] for name in names}
        for _index in range(draws):
            estimate = np.zeros(3)
            truth = rng.multivariate_normal(estimate, covariance)
            patterns = _patterns(estimate, covariance, radius)
            for name, points in patterns.items():
                hits[name].append(_hit(points, truth, radius))
                water[name].append(len(points) * DWELL_S)
        entry = {"sigma_m": float(sigma)}
        for name in names:
            hit_rate = float(np.mean(hits[name]))
            entry[name] = {
                "hit_rate": hit_rate,
                "hit_rate_std": float(np.sqrt(hit_rate * (1.0 - hit_rate) / draws)),
                "water_s": float(np.mean(water[name])),
                "n": draws,
            }
        rows.append(entry)
    return {
        "data": "合成数据",
        "seed": seed,
        "draws": draws,
        "radius_m": radius,
        "dwell_s": DWELL_S,
        "basis": BASIS,
        "sweep": rows,
        "note": "火点相对估计点按给定协方差抽取，不是现场喷射。",
    }


def _plot(payload: dict, directory: Path) -> None:
    configure_font()
    import matplotlib.pyplot as plt

    labels = {
        "fixed_point": "固定点",
        "fixed_sweep": "固定扫射",
        "adaptive_sweep": "自适应扫射",
    }
    colors = {"fixed_point": "#0072B2", "fixed_sweep": "#E69F00", "adaptive_sweep": "#009E73"}
    rows = payload["sweep"]
    sigmas = [row["sigma_m"] for row in rows]
    fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.6))
    for name in labels:
        axes[0].errorbar(
            sigmas,
            [row[name]["hit_rate"] for row in rows],
            yerr=[row[name]["hit_rate_std"] for row in rows],
            marker="o",
            capsize=3,
            color=colors[name],
            label=labels[name],
        )
        axes[1].plot(
            sigmas,
            [row[name]["water_s"] for row in rows],
            marker="o",
            color=colors[name],
            label=labels[name],
        )
    axes[0].set_xlabel("定位标准差 (m)")
    axes[0].set_ylabel("命中率")
    axes[0].set_ylim(0, 1)
    axes[1].set_xlabel("定位标准差 (m)")
    axes[1].set_ylabel("用水时长 (s)")
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle("喷射随定位协方差变化（合成数据）")
    fig.tight_layout()
    save_figure(fig, directory, "sigma-sweep")


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
