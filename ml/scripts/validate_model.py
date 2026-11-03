from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
import yaml
from PIL import Image, ImageDraw

from prepare_fire_smoke_v1 import sha256_file
from audit_yolo_dataset import label_path


def box_iou(a, b):
    left = np.maximum(a[:2], b[:2])
    right = np.minimum(a[2:], b[2:])
    intersection = np.maximum(right - left, 0).prod()
    return float(
        intersection
        / (
            np.maximum(a[2:] - a[:2], 0).prod()
            + np.maximum(b[2:] - b[:2], 0).prod()
            - intersection
        )
    )


def operating_metrics(records, thresholds, imgsz):
    counts = {name: Counter() for name in ("fire", "smoke")}
    errors, negative_images, negative_fp_images, detections = [], 0, 0, 0
    for record in records:
        gt = record["gt"]
        predictions = [p for p in record["pred"] if p[1] >= thresholds[int(p[0])]]
        matched = set()
        errors_before = sum(c["fp"] + c["fn"] for c in counts.values())
        if not gt:
            negative_images += 1
            negative_fp_images += bool(predictions)
            detections += len(predictions)
        for p in sorted(predictions, key=lambda p: -p[1]):
            cls = int(p[0])
            candidates = [
                (box_iou(np.array(p[2:]), np.array(g[1:])), j)
                for j, g in enumerate(gt)
                if int(g[0]) == cls and j not in matched
            ]
            score, index = max(candidates, default=(0.0, -1))
            count = counts[("fire", "smoke")[cls]]
            if score >= 0.5:
                count["tp"] += 1
                matched.add(index)
            else:
                count["fp"] += 1
        scale = imgsz / max(record["width"], record["height"])
        for j, g in enumerate(gt):
            count = counts[("fire", "smoke")[int(g[0])]]
            count["gt"] += 1
            count["fn"] += j not in matched
            if (g[3] - g[1]) * (g[4] - g[2]) * scale**2 < 32**2:
                count["small_gt"] += 1
                count["small_tp"] += j in matched
        if sum(c["fp"] + c["fn"] for c in counts.values()) > errors_before:
            errors.append(record["image"])
    per_class = {}
    for name, c in counts.items():
        per_class[name] = dict(
            c,
            precision=c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else None,
            recall=c["tp"] / c["gt"] if c["gt"] else None,
            small_recall_iou50=c["small_tp"] / c["small_gt"] if c["small_gt"] else None,
        )
    return dict(
        per_class=per_class,
        negative_images=negative_images,
        negative_fp_images=negative_fp_images,
        negative_image_fpr=negative_fp_images / negative_images
        if negative_images
        else None,
        negative_fp_detections=detections,
        error_images=errors,
    )


def predict_records(model, images, args, split):
    records = []
    listing = args.project / f"predict-{split}.txt"
    listing.write_text(
        "".join(f"{p.resolve().as_posix()}\n" for p in images), encoding="utf-8"
    )
    for result in model.predict(
        source=str(listing),
        stream=True,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        conf=0.001,
        iou=0.7,
        verbose=False,
    ):
        image = Path(result.path)
        label = label_path(image)
        height, width = result.orig_shape
        gt = []
        for line in label.read_text(encoding="utf-8").splitlines():
            cls, x, y, w, h = map(float, line.split())
            gt.append(
                [
                    int(cls),
                    (x - w / 2) * width,
                    (y - h / 2) * height,
                    (x + w / 2) * width,
                    (y + h / 2) * height,
                ]
            )
        pred = [
            [int(c), float(s), *map(float, b)]
            for c, s, b in zip(
                result.boxes.cls.cpu(), result.boxes.conf.cpu(), result.boxes.xyxy.cpu()
            )
        ]
        records.append(
            dict(image=str(image), width=width, height=height, gt=gt, pred=pred)
        )
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--data", type=Path, action="append", required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--device", default="0")
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    from ultralytics import YOLO

    model = YOLO(str(args.model.resolve()))
    if model.names != {0: "fire", 1: "smoke"}:
        raise ValueError(f"Wrong checkpoint class order: {model.names}")
    project = args.project.resolve()
    project.mkdir(parents=True, exist_ok=False)
    primary = args.data[0].resolve()
    config = yaml.safe_load(primary.read_text(encoding="utf-8"))
    root = Path(config["path"])
    if not root.is_absolute():
        root = (primary.parent / root).resolve()
    with (root / "manifest.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    validation = predict_records(
        model,
        [root / r["target_image"] for r in rows if r["split"] == "val"],
        args,
        "val",
    )
    thresholds = []
    for cls, name in enumerate(("fire", "smoke")):
        scores = []
        for threshold in np.arange(0.05, 0.951, 0.05):
            metric = operating_metrics(validation, [threshold, threshold], args.imgsz)[
                "per_class"
            ][name]
            tp, fp, fn = (metric.get(k, 0) for k in ("tp", "fp", "fn"))
            scores.append(
                (
                    2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0,
                    float(threshold),
                )
            )
        thresholds.append(max(scores)[1])
    tests = predict_records(
        model,
        [root / r["target_image"] for r in rows if r["split"] == "test"],
        args,
        "test",
    )
    record_by_path = {r["image"]: r for r in tests}
    summary = dict(
        model_sha256=sha256_file(args.model),
        manifest_sha256=sha256_file(root / "manifest.csv"),
        imgsz=args.imgsz,
        threshold_selection="per-class maximum F1 on val, IoU >= 0.5; ties choose higher confidence",
        thresholds=dict(zip(("fire", "smoke"), thresholds)),
        small_definition="box area after letterbox scaling < 32^2 pixels",
        datasets={},
    )
    for data_arg in args.data:
        data = data_arg.resolve()
        dataset_name = (
            data.stem + "_" + hashlib.sha256(str(data).encode()).hexdigest()[:8]
        )
        metrics = model.val(
            data=str(data),
            split="test",
            imgsz=args.imgsz,
            batch=args.batch,
            device=args.device,
            conf=0.001,
            iou=0.7,
            plots=True,
            save_json=False,
            project=str(project),
            name=dataset_name,
            exist_ok=False,
        )
        per_class = {}
        for pos, cls in enumerate(metrics.box.ap_class_index):
            per_class[model.names[int(cls)]] = dict(
                map50=float(metrics.box.ap50[pos]), map50_95=float(metrics.box.ap[pos])
            )
        group_config = yaml.safe_load(data.read_text(encoding="utf-8"))
        group_root = Path(group_config["path"])
        if not group_root.is_absolute():
            group_root = (data.parent / group_root).resolve()
        test_path = group_root / group_config["test"]
        if test_path.suffix == ".txt":
            selected_paths = [
                (group_root / line).resolve()
                for line in test_path.read_text().splitlines()
            ]
        else:
            selected_paths = [
                p.resolve()
                for p in test_path.rglob("*")
                if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
            ]
        selected = [record_by_path[str(p)] for p in selected_paths]
        summary["datasets"][dataset_name] = dict(
            data=str(data),
            data_sha256=sha256_file(data),
            map50=float(metrics.box.map50),
            map50_95=float(metrics.box.map),
            per_class=per_class,
            fixed_conf_025=operating_metrics(selected, [0.25, 0.25], args.imgsz),
            recommended=operating_metrics(selected, thresholds, args.imgsz),
        )
    errors = operating_metrics(tests, thresholds, args.imgsz)["error_images"]
    (project / "error_cases.json").write_text(
        json.dumps([record_by_path[p] for p in errors], indent=2), encoding="utf-8"
    )
    gallery = project / "errors"
    gallery.mkdir()
    for index, path in enumerate(errors[:40]):
        with Image.open(path) as im:
            canvas = im.convert("RGB")
            draw = ImageDraw.Draw(canvas)
            for cls, *box in record_by_path[path]["gt"]:
                draw.rectangle(box, outline="green", width=2)
            for cls, conf, *box in record_by_path[path]["pred"]:
                if conf >= thresholds[cls]:
                    draw.rectangle(box, outline="red", width=2)
            canvas.thumbnail((960, 960))
            canvas.save(gallery / f"{index:03d}_{Path(path).name}")
    if args.compare:
        baseline = json.loads(args.compare.read_text(encoding="utf-8"))
        if (
            baseline["manifest_sha256"] != summary["manifest_sha256"]
            or baseline["imgsz"] != args.imgsz
        ):
            raise ValueError("comparison requires the same manifest and imgsz")
        summary["comparison"] = dict(
            baseline_sha256=baseline["model_sha256"],
            map50_95_delta={
                key: value["map50_95"] - baseline["datasets"][key]["map50_95"]
                for key, value in summary["datasets"].items()
            },
        )
    lines = [
        "# YOLO validation",
        "",
        f"Model SHA-256: {summary['model_sha256']}",
        f"Manifest SHA-256: {summary['manifest_sha256']}",
        "",
        f"Validation-selected confidence: {summary['thresholds']}",
        "",
        "Small target: area after letterbox scaling < 32² pixels; recall at IoU 0.5.",
        "",
        "| Dataset | mAP50-95 | Fire recall @0.25 | Smoke recall @0.25 | Negative image FPR @0.25 | Δ mAP50-95 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key, item in summary["datasets"].items():
        point = item["fixed_conf_025"]
        delta = summary["comparison"]["map50_95_delta"][key] if args.compare else None
        lines.append(
            f"| {Path(item['data']).stem} | {item['map50_95']:.6f} | {point['per_class']['fire']['recall']} | {point['per_class']['smoke']['recall']} | {point['negative_image_fpr']} | {delta} |"
        )
    (project / "validation_report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    (project / "validation_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
