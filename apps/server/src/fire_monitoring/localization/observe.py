from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class SourceObservation:
    camera_id: int
    class_name: str
    pixel: tuple[float, float]
    covariance_px2: tuple[tuple[float, float], tuple[float, float]]
    reliability: float
    captured_at: datetime
    image_width: int
    image_height: int


def source_from_box(
    *,
    camera_id: int,
    class_name: str,
    bbox_xyxy: tuple[float, float, float, float],
    confidence: float,
    image_width: int,
    image_height: int,
    captured_at: datetime,
) -> SourceObservation:
    x1, y1, x2, y2 = bbox_xyxy
    if class_name == "fire":
        u, v = (x1 + x2) / 2, y2
    else:
        u, v = (x1 + x2) / 2, (y1 + y2) / 2
    u = min(max(u, 0), image_width - 1)
    v = min(max(v, 0), image_height - 1)
    sigma_u = max((x2 - x1) / 4, 1)
    sigma_v = max((y2 - y1) / 4, 1)
    reliability = min(max(confidence, 1e-3), 1 - 1e-3)
    return SourceObservation(
        camera_id=camera_id,
        class_name=class_name,
        pixel=(u, v),
        covariance_px2=((sigma_u * sigma_u, 0.0), (0.0, sigma_v * sigma_v)),
        reliability=reliability,
        captured_at=captured_at,
        image_width=image_width,
        image_height=image_height,
    )


def latest_in_window(
    observations: list[SourceObservation], now: datetime, window_ms: int
) -> list[SourceObservation]:
    cutoff = now - timedelta(milliseconds=window_ms)
    latest: dict[int, SourceObservation] = {}
    for item in observations:
        if item.captured_at < cutoff:
            continue
        current = latest.get(item.camera_id)
        if current is None or item.captured_at >= current.captured_at:
            latest[item.camera_id] = item
    return list(latest.values())


def write_manifest(
    directory: Path,
    landmark_sigma_px: float,
    frames: list,
    calibrations: dict,
    sources: list[SourceObservation],
) -> Path:
    frames_by_id = {frame.camera_id: frame for frame in frames}
    sources_by_id = {item.camera_id: item for item in sources}
    views = {}
    for camera_id in sorted(calibrations):
        frame = frames_by_id[camera_id]
        image_name = f"{camera_id}.jpg"
        (directory / image_name).write_bytes(frame.jpeg)
        calibration = calibrations[camera_id]
        view = {
            "image": image_name,
            "intrinsics": calibration["intrinsics"],
            "distortion": list(calibration["distortion"]),
            "landmarks": calibration["landmarks"],
        }
        source = sources_by_id.get(camera_id)
        if source is not None:
            view["source"] = {
                "pixel": [source.pixel[0], source.pixel[1]],
                "covariance_px2": [list(row) for row in source.covariance_px2],
                "reliability": source.reliability,
            }
        views[str(camera_id)] = view
    path = directory / "manifest.json"
    path.write_text(
        json.dumps({"landmark_sigma_px": landmark_sigma_px, "views": views}),
        encoding="utf-8",
    )
    return path


def localize_manifest(manifest: Path) -> dict:
    from fire_monitoring_inference.localization import localize

    return localize(manifest)


def locate_position(config, frames, calibrations, sources, localizer=None) -> dict:
    ready = {
        camera_id: calibration
        for camera_id, calibration in calibrations.items()
        if any(frame.camera_id == camera_id for frame in frames)
    }
    observed = [item for item in sources if item.camera_id in ready]
    if len(ready) < 2 or len({item.camera_id for item in observed}) < 2:
        return {"status": "UNOBSERVABLE", "support_camera_ids": []}
    run = localizer or localize_manifest
    with tempfile.TemporaryDirectory() as directory:
        manifest = write_manifest(
            Path(directory),
            config.localization.landmark_sigma_px,
            frames,
            ready,
            sources,
        )
        return run(manifest)
