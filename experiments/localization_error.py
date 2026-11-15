from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

from experiments.plotting import configure_font, require_file, save_figure, write_json
from fire_monitoring_inference.multiview_geometry import project, triangulate

COLUMNS = (
    "point_id",
    "camera_count",
    "truth_x_m",
    "truth_y_m",
    "truth_z_m",
    "est_x_m",
    "est_y_m",
    "est_z_m",
)


def _stats(errors: list[float]) -> dict:
    if not errors:
        raise SystemExit("分组里没有误差样本")
    values = np.asarray(errors, dtype=float)
    return {
        "n": int(values.size),
        "mean_m": float(np.mean(values)),
        "p90_m": float(np.quantile(values, 0.9)),
        "max_m": float(np.max(values)),
    }


def _cameras() -> tuple[np.ndarray, np.ndarray, list[np.ndarray]]:
    angles = np.arange(4) * np.pi / 2
    radius = np.full(4, 4.5)
    centers = np.column_stack(
        [radius * np.cos(angles), radius * np.sin(angles), np.full(4, 2.2)]
    )
    poses = []
    for center in centers:
        forward = -center.astype(float)
        forward /= np.linalg.norm(forward)
        right = np.cross(forward, [0.0, 0.0, 1.0])
        right /= np.linalg.norm(right)
        down = np.cross(forward, right)
        rotation = np.stack([right, down, forward])
        poses.append(np.r_[cv2.Rodrigues(rotation)[0].ravel(), -rotation @ center])
    intrinsics = np.array([[[800.0, 0, 640], [0, 800.0, 360], [0, 0, 1.0]]] * 4)
    distortion = [np.zeros(5) for _ in range(4)]
    return intrinsics, np.array(poses), distortion


def synthetic_rows(seed: int = 20261115, points: int = 12) -> list[dict]:
    rng = np.random.default_rng(seed)
    intrinsics, poses, distortion = _cameras()
    truth = rng.uniform([-0.8, -0.8, 0.2], [0.8, 0.8, 1.6], (points, 3))
    rows = []
    for point_id, point in enumerate(truth):
        pixels = project(point, intrinsics, distortion, poses)[0]
        for count in (2, 3, 4):
            noisy = pixels[:count] + rng.normal(0, 1.5, (count, 2))
            estimate, rank = triangulate(
                noisy, intrinsics[:count], distortion[:count], poses[:count]
            )
            if rank != 3:
                raise RuntimeError(f"点 {point_id} 用 {count} 路相机不能三角化")
            rows.append(
                {
                    "point_id": point_id,
                    "camera_count": count,
                    "truth_x_m": float(point[0]),
                    "truth_y_m": float(point[1]),
                    "truth_z_m": float(point[2]),
                    "est_x_m": float(estimate[0]),
                    "est_y_m": float(estimate[1]),
                    "est_z_m": float(estimate[2]),
                }
            )
    return rows


def read_rows(path: Path) -> list[dict]:
    require_file(path)
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or tuple(reader.fieldnames) != COLUMNS:
            raise SystemExit(f"定位 CSV 表头必须是：{','.join(COLUMNS)}")
        rows = list(reader)
    if not rows:
        raise SystemExit(f"{path} 没有数据行")
    parsed = []
    for row in rows:
        item = {"point_id": row["point_id"], "camera_count": int(row["camera_count"])}
        for name in COLUMNS[2:]:
            item[name] = float(row[name])
        if item["camera_count"] < 2:
            raise SystemExit("参与相机数至少为 2")
        parsed.append(item)
    return parsed


def _error(row: dict) -> float:
    truth = np.array([row["truth_x_m"], row["truth_y_m"], row["truth_z_m"]], dtype=float)
    estimate = np.array([row["est_x_m"], row["est_y_m"], row["est_z_m"]], dtype=float)
    return float(np.linalg.norm(estimate - truth))


def evaluate(rows: list[dict]) -> dict:
    errors = [_error(row) for row in rows]
    by_point: dict[str, list[float]] = defaultdict(list)
    by_cameras: dict[int, list[float]] = defaultdict(list)
    for row, error in zip(rows, errors, strict=True):
        by_point[str(row["point_id"])].append(error)
        by_cameras[int(row["camera_count"])].append(error)
    return {
        "overall": _stats(errors),
        "by_point": {key: _stats(values) for key, values in sorted(by_point.items())},
        "by_camera_count": {
            str(key): _stats(by_cameras[key]) for key in sorted(by_cameras)
        },
    }


def _plot(result: dict, directory: Path, title: str) -> None:
    configure_font()
    import matplotlib.pyplot as plt

    groups = result["by_camera_count"]
    labels = list(groups)
    mean = [groups[key]["mean_m"] for key in labels]
    p90 = [groups[key]["p90_m"] for key in labels]
    index = np.arange(len(labels))
    width = 0.36
    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    ax.bar(index - width / 2, mean, width, label="均值", color="#0072B2")
    ax.bar(index + width / 2, p90, width, label="P90", color="#E69F00")
    ax.set_xticks(index, [f"{key} 路" for key in labels])
    ax.set_ylabel("误差 (m)")
    ax.set_title(title)
    ax.legend(frameon=False)
    fig.tight_layout()
    save_figure(fig, directory, "error-by-cameras")


def run(rows: list[dict], out: Path, *, data: str, source: str) -> dict:
    result = evaluate(rows)
    title = "定位误差"
    if data == "合成数据":
        title = "定位误差（合成数据）"
    payload = {"data": data, "source": source, **result}
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "result.json", payload)
    _plot(result, out, title)
    return payload


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="定位误差：真值点与三角化结果")
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--seed", type=int, default=20261115)
    parser.add_argument("--points", type=int, default=12)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.synthetic == bool(args.csv):
        raise SystemExit("指定 --csv 或 --synthetic 其中之一")
    if args.synthetic:
        rows = synthetic_rows(args.seed, args.points)
        args.out.mkdir(parents=True, exist_ok=True)
        with (args.out / "input.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        run(rows, args.out, data="合成数据", source="multiview triangulate")
        return
    run(read_rows(args.csv), args.out, data="测量输入", source=str(args.csv))


if __name__ == "__main__":
    main()
