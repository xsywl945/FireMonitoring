#!/usr/bin/env python3
"""Evaluate one checkpoint on one or more independent YOLO test YAML files."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument(
        "--data",
        type=Path,
        action="append",
        required=True,
        help="Repeat --data for combined, D-Fire, and IFireSmoke test YAML files.",
    )
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--device", default="0")
    return parser.parse_args()


def safe_name(path: Path) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", path.stem)


def main() -> int:
    args = parse_args()
    model_path = args.model.expanduser().resolve()
    if not model_path.is_file():
        raise SystemExit(f"Model does not exist: {model_path}")

    from ultralytics import YOLO

    model = YOLO(str(model_path))
    project = args.project.expanduser().resolve()
    project.mkdir(parents=True, exist_ok=True)
    summary: dict[str, dict[str, object]] = {}

    for data_arg in args.data:
        data = data_arg.expanduser().resolve()
        if not data.is_file():
            raise SystemExit(f"Dataset YAML does not exist: {data}")
        dataset_name = safe_name(data)
        metrics = model.val(
            data=str(data),
            split="test",
            imgsz=args.imgsz,
            batch=args.batch,
            device=args.device,
            conf=0.001,
            iou=0.7,
            plots=True,
            save_json=True,
            project=str(project),
            name=dataset_name,
            exist_ok=False,
        )
        raw_names = getattr(model, "names", {})
        if isinstance(raw_names, list):
            class_names = {index: str(value) for index, value in enumerate(raw_names)}
        else:
            class_names = {int(index): str(value) for index, value in raw_names.items()}
        per_class = {
            name: {
                "class_id": class_id,
                "evaluated": False,
                "precision": None,
                "recall": None,
                "map50": None,
                "map50_95": None,
            }
            for class_id, name in sorted(class_names.items())
        }
        evaluated_ids = [int(value) for value in metrics.box.ap_class_index]
        for position, class_id in enumerate(evaluated_ids):
            class_name = class_names.get(class_id, f"class_{class_id}")
            per_class[class_name] = {
                "class_id": class_id,
                "evaluated": True,
                "precision": float(metrics.box.p[position]),
                "recall": float(metrics.box.r[position]),
                "map50": float(metrics.box.ap50[position]),
                "map50_95": float(metrics.box.ap[position]),
            }
        summary[dataset_name] = {
            "data": str(data),
            "class_names": class_names,
            "map50_95": float(metrics.box.map),
            "map50": float(metrics.box.map50),
            "map75": float(metrics.box.map75),
            "per_class": per_class,
            "results": {
                key: float(value) for key, value in metrics.results_dict.items()
            },
        }

    output = project / "validation_summary.json"
    output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Validation summary: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
