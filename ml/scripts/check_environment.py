#!/usr/bin/env python3
"""Verify that an AutoDL image can run CUDA training before money is spent."""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workdir",
        type=Path,
        default=Path("/root/autodl-tmp"),
        help="Data disk used for the free-space check.",
    )
    parser.add_argument(
        "--require-cuda",
        action="store_true",
        help="Return a non-zero exit code when CUDA is unavailable.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    problems: list[str] = []

    try:
        import torch
    except ImportError:
        print("ERROR: PyTorch is not installed. Choose an AutoDL PyTorch image.")
        return 1

    try:
        import ultralytics
    except ImportError:
        print(
            "ERROR: Ultralytics is not installed. Run: "
            "python -m pip install -r ml/requirements-autodl.txt"
        )
        return 1

    cuda_available = torch.cuda.is_available()
    gpu: dict[str, object] | None = None
    if cuda_available:
        try:
            device = torch.device("cuda:0")
            # A real operation catches the common RTX 5090/sm_120 wheel mismatch.
            result = torch.ones((256, 256), device=device) @ torch.ones(
                (256, 256), device=device
            )
            torch.cuda.synchronize()
            if float(result[0, 0].item()) != 256.0:
                problems.append("CUDA smoke calculation returned an unexpected value")
            properties = torch.cuda.get_device_properties(0)
            gpu = {
                "name": torch.cuda.get_device_name(0),
                "count": torch.cuda.device_count(),
                "compute_capability": list(torch.cuda.get_device_capability(0)),
                "memory_gib": round(properties.total_memory / 1024**3, 2),
                "torch_arch_list": torch.cuda.get_arch_list(),
            }
        except Exception as exc:  # noqa: BLE001 - diagnostics must report driver errors
            problems.append(f"CUDA smoke calculation failed: {exc}")
    elif args.require_cuda:
        problems.append("torch.cuda.is_available() is False")

    workdir = args.workdir.expanduser().resolve()
    disk_target = workdir if workdir.exists() else Path.cwd()
    disk = shutil.disk_usage(disk_target)
    report = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "ultralytics": ultralytics.__version__,
        "cuda_available": cuda_available,
        "gpu": gpu,
        "disk_checked": str(disk_target),
        "disk_free_gib": round(disk.free / 1024**3, 2),
        "problems": problems,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if problems:
        print("\nEnvironment check FAILED. Do not start paid training yet.")
        return 1
    print("\nEnvironment check PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
