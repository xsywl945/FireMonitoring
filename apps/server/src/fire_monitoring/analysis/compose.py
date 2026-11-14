from __future__ import annotations

from datetime import datetime

from fire_monitoring_inference.analysis.assess import assess
from fire_monitoring_inference.analysis.geometry import measurements
from fire_monitoring_inference.analysis.spread import analyze_spread
from fire_monitoring_inference.localization import localize

from ..localization.observe import SourceObservation, locate_position


def _sample_dicts(samples: list) -> list[dict]:
    if not samples:
        return []
    origin = min(item.captured_at for item in samples)
    return [
        {
            "t": (item.captured_at - origin).total_seconds(),
            "captured_at": item.captured_at,
            "camera_id": item.camera_id,
            "bbox": list(item.bbox),
            "width": item.width,
            "height": item.height,
        }
        for item in samples
    ]


def _edge_source(sample: dict, side: str) -> SourceObservation:
    x1, y1, x2, y2 = sample["bbox"]
    pixel = (x1 if side == "left" else x2, y2)
    width = sample["width"]
    height = sample["height"]
    u = min(max(pixel[0], 0), width - 1)
    v = min(max(pixel[1], 0), height - 1)
    sigma_u = max((x2 - x1) / 4, 1)
    sigma_v = max((y2 - y1) / 4, 1)
    return SourceObservation(
        camera_id=sample["camera_id"],
        class_name="fire",
        pixel=(u, v),
        covariance_px2=((sigma_u * sigma_u, 0.0), (0.0, sigma_v * sigma_v)),
        reliability=0.8,
        captured_at=sample["captured_at"],
        image_width=width,
        image_height=height,
    )


def _groups(samples: list[dict]) -> list[list[dict]]:
    grouped: dict[int, list[dict]] = {}
    for sample in samples:
        grouped.setdefault(round(sample["t"] * 2), []).append(sample)
    return [grouped[key] for key in sorted(grouped)]


def _footprints(
    config,
    frames,
    calibrations,
    samples: list[dict],
    localizer,
) -> list[dict]:
    usable = [
        group
        for group in _groups(samples)
        if len({item["camera_id"] for item in group if item["camera_id"] in calibrations})
        >= 2
    ]
    if not usable:
        return []
    chosen = [usable[0], usable[-1]] if len(usable) > 1 else usable
    tracks = []
    for group in chosen:
        ready = [item for item in group if item["camera_id"] in calibrations]
        left = locate_position(
            config,
            frames,
            calibrations,
            [_edge_source(item, "left") for item in ready],
            localizer=localizer,
        )
        right = locate_position(
            config,
            frames,
            calibrations,
            [_edge_source(item, "right") for item in ready],
            localizer=localizer,
        )
        if left.get("status") != "ESTIMATED" or right.get("status") != "ESTIMATED":
            continue
        tracks.append(
            {
                "t": ready[-1]["t"],
                "left": [left["xyz"][0], left["xyz"][1]],
                "right": [right["xyz"][0], right["xyz"][1]],
            }
        )
    return tracks


def compose(
    config,
    *,
    call: dict | None,
    room_name: str,
    configured_scene: str,
    position: dict | None,
    samples: list,
    frames: list,
    calibrations: dict,
    combustibles: list,
    localizer=None,
) -> dict:
    plain = _sample_dicts(samples)
    prepared = measurements(
        position=position,
        samples=plain,
        calibrations=calibrations,
        sigma=config.localization.landmark_sigma_px,
    )
    tracks = _footprints(
        config,
        frames,
        calibrations,
        plain,
        localizer or localize,
    )
    spread = analyze_spread(tracks, combustibles) if tracks else None
    evidence = None if call is None else call.get("evidence")
    observed = None if evidence is None else evidence["scene_type"]
    document = assess(
        call,
        configured_scene=configured_scene,
        location=room_name,
        prepared=prepared,
        spread=spread,
        observed_scene=observed,
    )
    document["inputs"] = {
        "samples": [
            {
                "captured_at": item.captured_at.isoformat(),
                "camera_id": item.camera_id,
                "bbox": list(item.bbox),
                "width": item.width,
                "height": item.height,
            }
            for item in samples
        ]
    }
    return document


def samples_from_inputs(raw: list[dict]) -> list:
    from ..detection.ingest import FireSample

    return [
        FireSample(
            captured_at=datetime.fromisoformat(item["captured_at"]),
            camera_id=item["camera_id"],
            bbox=tuple(item["bbox"]),
            width=item["width"],
            height=item["height"],
        )
        for item in raw
    ]
