from __future__ import annotations

import argparse
import json

import numpy as np

from .ballistics import fit_drag
from .calibrate import LaserSample, fit_gimbal
from .kinematics import GimbalParams


def _samples(path: str) -> list[dict]:
    return json.loads(open(path, encoding="utf-8").read())


def _calibrate(args: argparse.Namespace) -> None:
    p0 = [float(item) for item in args.p0.split(",")]
    initial = GimbalParams.nominal(p0, yaw=np.deg2rad(args.yaw_deg), tilt_zero=args.tilt_zero)
    samples = [
        LaserSample(item["pan_cdeg"], item["tilt_cdeg"], np.array(item["xyz"], dtype=float))
        for item in _samples(args.samples)
    ]
    fitted = fit_gimbal(samples, initial)
    print(
        json.dumps(
            {"params": fitted.params.to_dict(), "residuals_m": fitted.residuals_m},
            ensure_ascii=False,
        )
    )


def _drag(args: argparse.Namespace) -> None:
    shots = [
        (np.deg2rad(item["pitch_deg"]), float(item["range_m"])) for item in _samples(args.samples)
    ]
    fitted = fit_drag(shots)
    print(json.dumps({"speed": fitted.speed, "drag": fitted.drag}))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="fire-suppression")
    commands = parser.add_subparsers(dest="cmd", required=True)
    calibrate = commands.add_parser("calibrate")
    calibrate.add_argument("--p0", required=True, help="rough pivot x,y,z in metres")
    calibrate.add_argument("--yaw-deg", type=float, default=0.0)
    calibrate.add_argument("--tilt-zero", type=float, default=0.0)
    calibrate.add_argument("--samples", required=True)
    calibrate.set_defaults(func=_calibrate)
    drag = commands.add_parser("fit-drag")
    drag.add_argument("--samples", required=True)
    drag.set_defaults(func=_drag)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
