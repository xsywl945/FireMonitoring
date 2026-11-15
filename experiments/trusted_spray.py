from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from experiments.plotting import configure_font, save_figure, write_json
from fire_monitoring_inference.multiview_geometry import calibrate, locate, project
from fire_monitoring_inference.suppression.coverage import cover_probability
from fire_monitoring_inference.suppression.feedback import zigzag

DWELL_S = 1.0
OPERATING_RADIUS_M = 0.2
RADII_M = (0.01, 0.02, 0.05, 0.1, 0.2, 0.4)
FIXED_COVARIANCE = np.diag([0.3**2, 0.3**2, 0.02**2])


def _union_probability(
    points: list[np.ndarray], mean: np.ndarray, covariance: np.ndarray, radius: float, seed: int
) -> float:
    draws = np.random.default_rng(seed).multivariate_normal(np.asarray(mean, dtype=float), covariance, size=2000)
    distance = np.linalg.norm(draws[:, None, :] - np.asarray(points, dtype=float)[None, :, :], axis=2)
    return float(np.mean(np.any(distance <= radius, axis=1)))


def _strategy(points: list[np.ndarray], truth: np.ndarray, radius: float) -> dict:
    hits = [float(np.linalg.norm(point - truth)) <= radius for point in points]
    first = next((index for index, hit in enumerate(hits) if hit), None)
    return {
        "hit": any(hits),
        "water_s": len(points) * DWELL_S,
        "first_hit_s": None if first is None else first * DWELL_S,
        "points": len(points),
    }


def localize_trials(count: int, seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    cv2.setRNGSeed(int(seed) % (2**31))
    world = rng.uniform([-1, -1, 0], [1, 1, 2], (24, 3))
    trials = []
    for event in range(count):
        angles = np.arange(4) * np.pi / 2 + rng.uniform(-0.4, 0.4, 4)
        radius = rng.uniform(3.2, 5.5, 4)
        centers = np.column_stack(
            [
                radius * np.cos(angles),
                radius * np.sin(angles),
                rng.uniform(1.2, 3.0, 4),
            ]
        )
        poses = []
        for center in centers:
            forward = np.array([0.0, 0.0, 1.0]) - center
            forward /= np.linalg.norm(forward)
            right = np.cross(forward, [0.0, 0.0, 1.0])
            right /= np.linalg.norm(right)
            rotation = np.stack([right, np.cross(forward, right), forward])
            rotation = (
                Rotation.from_euler(
                    "xyz", [*rng.uniform(-0.12, 0.12, 2), rng.uniform(-0.5, 0.5)]
                ).as_matrix()
                @ rotation
            )
            poses.append(np.r_[cv2.Rodrigues(rotation)[0].ravel(), -rotation @ center])
        poses = np.array(poses)
        focal = rng.uniform(700, 900, 4)
        intrinsics = np.array([[[f, 0, 640], [0, f, 360], [0, 0, 1.0]] for f in focal])
        distortion = np.zeros((4, 5))
        observations, landmarks = [], []
        for camera_k, pose in zip(intrinsics, poses, strict=True):
            uv = cv2.projectPoints(world, pose[:3], pose[3:], camera_k, None)[0].reshape(-1, 2)
            keep = ((uv > [0, 0]) & (uv < [1280, 720])).all(axis=1)
            if int(keep.sum()) < 8:
                raise RuntimeError("控制点可见数量不足")
            landmarks.append(world[keep])
            observations.append(uv[keep] + rng.normal(0, 1.0, (int(keep.sum()), 2)))
        estimated, covariance = calibrate(landmarks, observations, intrinsics, distortion, 1.0)
        source = rng.uniform([-0.4, -0.4, 0.3], [0.4, 0.4, 1.5])
        truth_pixels = project(source, intrinsics, distortion, poses)[0]
        visible = ((truth_pixels > [0, 0]) & (truth_pixels < [1280, 720])).all(axis=1)
        if not visible.all():
            raise RuntimeError("火点不在四路画面内")
        pixels = truth_pixels + rng.normal(0, 1.5, (4, 2))
        result = locate(
            pixels,
            intrinsics,
            distortion,
            estimated,
            covariance,
            np.tile(4 * np.eye(2), (4, 1, 1)),
            np.full(4, 1280 * 720),
            np.full(4, 0.95),
        )
        if result["status"] != "ESTIMATED":
            raise RuntimeError("合成定位不可观测")
        trials.append(
            {
                "truth": source,
                "xyz": np.array(result["xyz"], dtype=float),
                "covariance": np.array(result["covariance"], dtype=float),
            }
        )
    return trials


def _patterns(estimate: np.ndarray, covariance: np.ndarray, radius: float) -> dict[str, list[np.ndarray]]:
    return {
        "fixed_point": [estimate],
        "fixed_sweep": zigzag(estimate, FIXED_COVARIANCE, radius),
        "adaptive_sweep": zigzag(estimate, covariance, radius),
    }


def score_trials(trials: list[dict], radius: float) -> dict:
    names = ("fixed_point", "fixed_sweep", "adaptive_sweep")
    bucket = {
        name: {"hit": [], "water_s": [], "first_hit_s": []} for name in names
    }
    for index, trial in enumerate(trials):
        patterns = _patterns(trial["xyz"], trial["covariance"], radius)
        for name, points in patterns.items():
            outcome = _strategy(points, trial["truth"], radius)
            bucket[name]["hit"].append(outcome["hit"])
            bucket[name]["water_s"].append(outcome["water_s"])
            if outcome["first_hit_s"] is not None:
                bucket[name]["first_hit_s"].append(outcome["first_hit_s"])
    summary = {}
    for name, item in bucket.items():
        hits = item["first_hit_s"]
        summary[name] = {
            "hit_rate": float(np.mean(item["hit"])),
            "water_s_mean": float(np.mean(item["water_s"])),
            "first_hit_s_mean": None if not hits else float(np.mean(hits)),
            "hits": int(np.sum(item["hit"])),
            "n": len(item["hit"]),
        }
    return summary


def calibration_pairs(trials: list[dict], seed: int) -> list[dict]:
    rows = []
    for index, trial in enumerate(trials):
        covariance = trial["covariance"]
        for radius in RADII_M:
            patterns = _patterns(trial["xyz"], trial["covariance"], radius)
            nominal = {
                "fixed_point": cover_probability(covariance, radius, samples=2000, seed=seed + index),
                "fixed_sweep": _union_probability(
                    patterns["fixed_sweep"], trial["xyz"], covariance, radius, seed + 1000 + index
                ),
                "adaptive_sweep": _union_probability(
                    patterns["adaptive_sweep"], trial["xyz"], covariance, radius, seed + 2000 + index
                ),
            }
            for name, points in patterns.items():
                hit = _strategy(points, trial["truth"], radius)["hit"]
                rows.append(
                    {
                        "method": name,
                        "radius_m": radius,
                        "nominal": nominal[name],
                        "hit": bool(hit),
                    }
                )
    return rows


def _bins(rows: list[dict]) -> dict[str, list[dict]]:
    edges = (0.0, 0.2, 0.4, 0.6, 0.8, 1.01)
    grouped: dict[str, dict[str, list[dict]]] = {}
    for row in rows:
        for low, high in zip(edges, edges[1:]):
            if low <= row["nominal"] < high:
                key = f"{low:.1f}-{min(high, 1):.1f}"
                grouped.setdefault(row["method"], {}).setdefault(key, []).append(row)
                break
    if not grouped:
        raise SystemExit("校准曲线没有样本")
    result = {}
    for method, bins in grouped.items():
        result[method] = [
            {
                "bin": key,
                "n": len(chosen),
                "nominal_mean": float(np.mean([item["nominal"] for item in chosen])),
                "hit_rate": float(np.mean([item["hit"] for item in chosen])),
            }
            for key, chosen in sorted(bins.items())
        ]
    return result


def run(count: int, seed: int) -> dict:
    trials = localize_trials(count, seed)
    return {
        "data": "合成数据",
        "seed": seed,
        "trials": count,
        "dwell_s": DWELL_S,
        "operating_radius_m": OPERATING_RADIUS_M,
        "strategies": score_trials(trials, OPERATING_RADIUS_M),
        "calibration": _bins(calibration_pairs(trials, seed)),
        "note": "火点位置和协方差来自可变布局合成定位，不是现场喷射。",
    }


def _plot(payload: dict, directory: Path) -> None:
    configure_font()
    import matplotlib.pyplot as plt

    labels = {
        "fixed_point": "固定点",
        "fixed_sweep": "固定扫射",
        "adaptive_sweep": "自适应扫射",
    }
    names = list(labels)
    strategies = payload["strategies"]
    index = np.arange(len(names))
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.6))
    axes[0].bar(index, [strategies[name]["hit_rate"] for name in names], color="#0072B2")
    axes[0].set_xticks(index, [labels[name] for name in names])
    axes[0].set_ylim(0, 1)
    axes[0].set_ylabel("命中率")
    axes[1].bar(index, [strategies[name]["water_s_mean"] for name in names], color="#009E73")
    axes[1].set_xticks(index, [labels[name] for name in names])
    axes[1].set_ylabel("用水时长 (s)")
    fig.suptitle("三种喷射（合成数据）")
    fig.tight_layout()
    save_figure(fig, directory, "hit-rate")

    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    colors = {"fixed_point": "#0072B2", "fixed_sweep": "#E69F00", "adaptive_sweep": "#009E73"}
    ax.plot([0, 1], [0, 1], color="#999999", linewidth=1)
    for name, curve in payload["calibration"].items():
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
    ax.legend(frameon=False)
    fig.tight_layout()
    save_figure(fig, directory, "calibration")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="可信喷射的合成覆盖实验")
    parser.add_argument("--trials", type=int, default=16)
    parser.add_argument("--seed", type=int, default=20261115)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.trials < 1:
        raise SystemExit("试验次数至少为 1")
    payload = run(args.trials, args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    write_json(args.out / "result.json", payload)
    _plot(payload, args.out)


if __name__ == "__main__":
    main()
