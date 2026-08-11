#!/usr/bin/env python3
"""Train the reproducible two-class fire/smoke YOLO baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True, help="Dataset YAML path.")
    parser.add_argument("--model", default="yolo11s.pt")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument(
        "--batch",
        type=float,
        default=0.70,
        help="GPU-memory fraction. Use an integer-looking float such as 32 for fixed batch.",
    )
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--device", default="0")
    parser.add_argument("--fraction", type=float, default=1.0)
    parser.add_argument(
        "--cache",
        choices=("ram", "disk", "none"),
        default="ram",
        help="Dataset cache location. AutoDL defaults to RAM to protect the 50 GB data disk.",
    )
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_metadata() -> dict[str, object]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        return {"git_commit": commit, "git_dirty": dirty}
    except (FileNotFoundError, subprocess.CalledProcessError):
        return {"git_commit": None, "git_dirty": None}


def bundle_metadata() -> dict[str, object]:
    bundle_file = Path(__file__).resolve().parents[2] / "BUNDLE-MANIFEST.txt"
    if not bundle_file.is_file():
        return {"bundle_manifest": None, "bundle_metadata": None}
    metadata: dict[str, str] = {}
    for line in bundle_file.read_text(encoding="utf-8-sig").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            metadata[key] = value
    return {
        "bundle_manifest": str(bundle_file),
        "bundle_metadata": metadata,
    }


def main() -> int:
    args = parse_args()
    data = args.data.expanduser().resolve()
    project = args.project.expanduser().resolve()
    requested_run = project / args.name
    if not data.is_file():
        print(f"ERROR: dataset YAML does not exist: {data}", file=sys.stderr)
        return 2
    if requested_run.exists():
        print(
            f"ERROR: run directory already exists: {requested_run}\n"
            "Use a new --name so an earlier experiment is never overwritten.",
            file=sys.stderr,
        )
        return 2
    if not (0 < args.fraction <= 1):
        print("ERROR: --fraction must be in (0, 1].", file=sys.stderr)
        return 2

    import torch
    import ultralytics
    from ultralytics import YOLO

    project.mkdir(parents=True, exist_ok=True)
    manifest = data.parent / "manifest.csv"
    model_file = Path(args.model).expanduser()
    if model_file.is_file():
        model_file = model_file.resolve()
    config = {
        **vars(args),
        "data": str(data),
        "project": str(project),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "ultralytics": ultralytics.__version__,
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "dataset_yaml_sha256": sha256_file(data),
        "dataset_manifest": str(manifest) if manifest.is_file() else None,
        "dataset_manifest_sha256": sha256_file(manifest) if manifest.is_file() else None,
        "pretrained_model_file": str(model_file) if model_file.is_file() else None,
        "pretrained_model_sha256": (
            sha256_file(model_file) if model_file.is_file() else None
        ),
        **git_metadata(),
        **bundle_metadata(),
    }
    request_file = project / f"{args.name}.request.json"
    request_file.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    batch: int | float
    batch = int(args.batch) if args.batch >= 1 and args.batch.is_integer() else args.batch
    cache: str | bool = False if args.cache == "none" else args.cache
    model = YOLO(args.model)
    results = model.train(
        data=str(data),
        epochs=args.epochs,
        patience=args.patience,
        imgsz=args.imgsz,
        batch=batch,
        device=args.device,
        workers=args.workers,
        project=str(project),
        name=args.name,
        exist_ok=False,
        cache=cache,
        amp=True,
        optimizer="auto",
        cos_lr=True,
        seed=args.seed,
        deterministic=True,
        fraction=args.fraction,
        save=True,
        save_period=5,
        plots=True,
        close_mosaic=10,
        mosaic=0.5,
        mixup=0.0,
        degrees=3.0,
        translate=0.1,
        scale=0.4,
        fliplr=0.5,
        flipud=0.0,
        compile=False,
    )

    save_dir = Path(getattr(results, "save_dir", requested_run))
    if not save_dir.exists() and getattr(model, "trainer", None) is not None:
        save_dir = Path(model.trainer.save_dir)
    config["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    config["save_dir"] = str(save_dir)
    (save_dir / "experiment.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Training finished. Best checkpoint: {save_dir / 'weights' / 'best.pt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
