from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2

from fire_monitoring.calibration.pdf import charuco_pdf, marker_pdf
from fire_monitoring.calibration.service import write_extrinsics, write_intrinsics
from fire_monitoring.config import load_config
from fire_monitoring.db import make_engine, make_session_factory, mysql_url
from fire_monitoring.models import Camera


def _read_image(path: Path):
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"无法读取图片 {path}")
    return image


def _camera(session, camera_id: int) -> Camera:
    camera = session.get(Camera, camera_id)
    if camera is None:
        raise ValueError(f"摄像头 {camera_id} 不存在")
    return camera


def _session(config_path: Path):
    config = load_config(config_path)
    engine = make_engine(mysql_url(config))
    session = make_session_factory(engine)()
    return config, session


def _boards(args: argparse.Namespace) -> None:
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    for name in ("a4", "a3"):
        (out / f"charuco-{name}.pdf").write_bytes(charuco_pdf(name))
        (out / f"markers-{name}.pdf").write_bytes(marker_pdf(name))
    print(out)


def _intrinsics(args: argparse.Namespace) -> None:
    _config, session = _session(args.config)
    try:
        camera = _camera(session, args.camera_id)
        document = write_intrinsics(camera, [_read_image(path) for path in args.images], args.paper)
        session.commit()
    finally:
        session.close()
    print(json.dumps({"camera_id": args.camera_id, "rms": document["intrinsics_reprojection_error_px"]}, ensure_ascii=False))


def _extrinsics(args: argparse.Namespace) -> None:
    config, session = _session(args.config)
    try:
        camera = _camera(session, args.camera_id)
        raw = json.loads(args.points.read_text(encoding="utf-8"))
        worlds = {int(item["marker_id"]): tuple(item["world_m"]) for item in raw}
        document = write_extrinsics(
            camera,
            _read_image(args.image),
            worlds,
            config.localization.landmark_sigma_px,
        )
        session.commit()
    finally:
        session.close()
    print(json.dumps({"camera_id": args.camera_id, "rms": document["extrinsics_reprojection_error_px"]}, ensure_ascii=False))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m fire_monitoring.calibration")
    commands = parser.add_subparsers(dest="command", required=True)

    boards = commands.add_parser("boards")
    boards.add_argument("--out", type=Path, required=True)
    boards.set_defaults(func=_boards)

    intrinsics = commands.add_parser("intrinsics")
    intrinsics.add_argument("--config", type=Path, required=True)
    intrinsics.add_argument("--camera-id", type=int, required=True)
    intrinsics.add_argument("--paper", choices=("a4", "a3"), required=True)
    intrinsics.add_argument("images", nargs="+", type=Path)
    intrinsics.set_defaults(func=_intrinsics)

    extrinsics = commands.add_parser("extrinsics")
    extrinsics.add_argument("--config", type=Path, required=True)
    extrinsics.add_argument("--camera-id", type=int, required=True)
    extrinsics.add_argument("--image", type=Path, required=True)
    extrinsics.add_argument("--points", type=Path, required=True)
    extrinsics.set_defaults(func=_extrinsics)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
