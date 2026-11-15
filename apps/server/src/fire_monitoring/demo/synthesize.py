from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

import cv2
import numpy as np

from .geometry import (
    DEPTH_M,
    FPS,
    GIMBAL_P0,
    GIMBAL_TILT_ZERO,
    GIMBAL_YAW_DEG,
    GROW_S,
    HEIGHT_M,
    PENDING_S,
    IMAGE_H,
    IMAGE_W,
    WIDTH_M,
    VirtualCamera,
    billboard,
    box_of,
    build_cameras,
    frame_count,
    frame_time,
)
from .render import composite, static_scene

PACK = Path(__file__).resolve().parents[5] / "data" / "demo" / "synthetic-classroom"
NOTE = "虚拟教室、程序火焰和手写千问响应。这是合成数据，不是现场录像，也不是模型在线输出。"

SCRIPTS = (
    {
        "id": "full",
        "title": "完整灭火",
        "duration_s": 60.0,
        "fire_xyz": [4.0, 2.70, 0.76],
        "smoke_at": 8.0,
        "fire_at": 22.0,
        "gone_at": 45.0,
        "person": None,
        "evidence": "ordinary",
    },
    {
        "id": "electrical",
        "title": "带电火灾禁水",
        "duration_s": 42.0,
        "fire_xyz": [5.85, 3.05, 1.20],
        "smoke_at": 6.0,
        "fire_at": 16.0,
        "gone_at": None,
        "person": None,
        "evidence": "electrical",
    },
    {
        "id": "person",
        "title": "有人避让",
        "duration_s": 42.0,
        "fire_xyz": [4.0, 2.70, 0.76],
        "smoke_at": 6.0,
        "fire_at": 16.0,
        "gone_at": None,
        "person": [5.05, 2.95, 0.0],
        "evidence": "person",
    },
)


def _spray_at(script: dict) -> float | None:
    if script["gone_at"] is None:
        return None
    return script["fire_at"] + GROW_S + PENDING_S


def _flame(script: dict, moment: float) -> tuple[np.ndarray, float, float] | None:
    start = script["fire_at"]
    if moment < start:
        return None
    age = moment - start
    height = min(1.05, 0.16 + 0.0032 * age * age)
    diameter = 0.42 * height
    spray = _spray_at(script)
    gone = script["gone_at"]
    if spray is not None and gone is not None and moment >= spray:
        if moment >= gone:
            return None
        scale = ((gone - moment) / (gone - spray)) ** 2
        height *= scale
        diameter *= scale
        if height < 0.05:
            return None
    return np.array(script["fire_xyz"], dtype=float), height, diameter


def _smoke(script: dict, moment: float) -> tuple[np.ndarray, float] | None:
    if moment < script["smoke_at"]:
        return None
    if script["gone_at"] is not None and moment >= script["gone_at"]:
        return None
    base = np.array(script["fire_xyz"], dtype=float)
    return base + np.array([0.0, 0.0, 0.55]), 0.55


def _evidence(kind: str) -> dict:
    shared = {
        "schema_version": "4.0",
        "liquid": False,
        "oil_pan": False,
        "metal_powder": False,
        "scene_type": "classroom",
        "smoke_color": "gray",
        "smoke_density": "light",
        "uncertainties": ["手写的合成响应，不是千问看过画面后的输出"],
    }
    if kind == "electrical":
        shared.update(
            {
                "burning_objects": [
                    {
                        "frame_index": 1,
                        "name": "配电箱",
                        "evidence": "东墙配电箱门缝有明火，箱体带电",
                    }
                ],
                "suspected_cause": "electrical_short",
                "energized_equipment": True,
                "person_count": 0,
                "person_location": "画面中没有人",
            }
        )
    elif kind == "person":
        shared.update(
            {
                "burning_objects": [
                    {"frame_index": 1, "name": "课桌", "evidence": "前排课桌桌面有明火，纸张卷曲"}
                ],
                "suspected_cause": "open_flame",
                "energized_equipment": False,
                "person_count": 1,
                "person_location": "一名站立的人在火点旁约一米",
            }
        )
    else:
        shared.update(
            {
                "burning_objects": [
                    {"frame_index": 1, "name": "课桌", "evidence": "前排课桌桌面有明火，纸张卷曲"}
                ],
                "suspected_cause": "open_flame",
                "energized_equipment": False,
                "person_count": 0,
                "person_location": "画面中没有人",
            }
        )
    return shared


def _camera_document(camera: VirtualCamera) -> dict:
    return {
        "key": camera.key,
        "name": camera.name,
        "slot": camera.slot,
        "time_offset_ms": camera.offset_ms,
        "eye_m": camera.eye.tolist(),
        "right": camera.right.tolist(),
        "up": (-camera.down).tolist(),
        "forward": camera.forward.tolist(),
        "fov_y_deg": camera.fov_y_deg(),
        "intrinsics": camera.intrinsics.tolist(),
        "distortion": camera.distortion.tolist(),
        "landmarks": camera.landmarks,
    }


def _check_aim(script: dict) -> None:
    from fire_monitoring_inference.suppression.aim import solve_aim
    from fire_monitoring_inference.suppression.kinematics import GimbalParams

    gimbal = GimbalParams.nominal(
        list(GIMBAL_P0),
        yaw=math.radians(GIMBAL_YAW_DEG),
        tilt_zero=GIMBAL_TILT_ZERO,
    )
    aim = solve_aim(gimbal, np.array(script["fire_xyz"], dtype=float), 10.0, 0.05)
    if aim is None:
        raise RuntimeError(f"{script['id']} 的火点不在水柱射程内")


def _check_localization(cameras: list[VirtualCamera], script: dict) -> None:
    from fire_monitoring_inference.localization import localize

    root = Path("/tmp/fire-demo-localize") / script["id"]
    root.mkdir(parents=True, exist_ok=True)
    views = {}
    blank = np.full((IMAGE_H, IMAGE_W, 3), 180, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", blank)
    if not ok:
        raise RuntimeError("jpeg encode failed")
    flame = _flame(script, script["fire_at"] + 4)
    if flame is None:
        raise RuntimeError("定位检查时没有火焰")
    base, height, diameter = flame
    for camera in cameras:
        name = f"{camera.key}.jpg"
        (root / name).write_bytes(encoded.tobytes())
        box = box_of(camera, billboard(camera, base, height, diameter))
        if box is None:
            raise RuntimeError(f"{script['id']} 的火点在 {camera.name} 相机外")
        x1, y1, x2, y2 = box
        views[str(camera.slot)] = {
            "image": name,
            "intrinsics": camera.intrinsics.tolist(),
            "distortion": camera.distortion.tolist(),
            "landmarks": camera.landmarks,
            "source": {
                "pixel": [(x1 + x2) / 2, y2],
                "covariance_px2": [[4.0, 0.0], [0.0, 4.0]],
                "reliability": 0.9,
            },
        }
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps({"landmark_sigma_px": 2.0, "views": views}), encoding="utf-8")
    found = localize(manifest)
    if found.get("status") != "ESTIMATED":
        raise RuntimeError(f"{script['id']} 定位失败: {found}")
    error = float(np.linalg.norm(np.array(found["xyz"]) - np.array(script["fire_xyz"])))
    if error > 0.25:
        raise RuntimeError(f"{script['id']} 火点误差 {error:.3f} m，定位 {found['xyz']}")
    print(f"{script['id']} 定位误差 {error:.3f} m", flush=True)


def _encode(path: Path, frames) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{IMAGE_W}x{IMAGE_H}",
        "-r",
        str(FPS),
        "-i",
        "-",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "32",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(path),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdin is not None
    for frame in frames:
        process.stdin.write(np.ascontiguousarray(frame).tobytes())
    process.stdin.close()
    error = process.stderr.read().decode() if process.stderr is not None else ""
    if process.wait() != 0:
        raise RuntimeError(error or "ffmpeg failed")


def _frames(camera: VirtualCamera, script: dict, background: np.ndarray, records: list[dict]):
    count = frame_count(script["duration_s"])
    person = None if script["person"] is None else np.array(script["person"], dtype=float)
    for index in range(count):
        moment = frame_time(index)
        local = moment + camera.offset_ms / 1000
        flame = _flame(script, local)
        smoke = _smoke(script, local)
        shown_person = person if person is not None and local >= script["fire_at"] else None
        boxes = []
        if smoke is not None:
            origin, size = smoke
            box = box_of(camera, billboard(camera, origin, size * 0.7, size * 2))
            if box is not None:
                boxes.append({"class_name": "smoke", "confidence": 0.82, "bbox": box})
        if flame is not None:
            base, height, diameter = flame
            box = box_of(camera, billboard(camera, base, height, diameter))
            spray = _spray_at(script)
            if box is None and (spray is None or local < spray):
                raise RuntimeError(f"{script['id']} 第 {index} 帧在 {camera.name} 看不到火")
            if box is None:
                flame = None
            else:
                boxes.append({"class_name": "fire", "confidence": 0.91, "bbox": box})
        if shown_person is not None:
            box = box_of(camera, billboard(camera, shown_person, 1.7, 0.44))
            if box is not None:
                boxes.append({"class_name": "person", "confidence": 0.88, "bbox": box})
        records[index]["cameras"][camera.key] = boxes
        if camera.slot == 1:
            records[index]["persons"] = [] if shown_person is None else [shown_person.tolist()]
        yield composite(
            camera,
            background,
            flame=flame,
            smoke=smoke,
            person=shown_person,
        )


def _write_script(root: Path, cameras: list[VirtualCamera], script: dict) -> dict:
    count = frame_count(script["duration_s"])
    records = [{"t": frame_time(index), "cameras": {}, "persons": []} for index in range(count)]
    videos = {}
    for camera in cameras:
        background, _depth = static_scene(camera)
        relative = f"videos/{script['id']}-{camera.key}.mp4"
        _encode(root / relative, _frames(camera, script, background, records))
        videos[camera.key] = relative
    detection = f"detections/{script['id']}.json"
    qwen = f"qwen/{script['id']}.json"
    (root / detection).parent.mkdir(parents=True, exist_ok=True)
    (root / detection).write_text(
        json.dumps(
            {
                "synthetic": True,
                "note": "检测框由投影几何生成，不是 YOLO 的输出。",
                "fps": FPS,
                "frames": records,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / qwen).parent.mkdir(parents=True, exist_ok=True)
    (root / qwen).write_text(
        json.dumps(
            {
                "synthetic": True,
                "handwritten": True,
                "note": "手写的合成响应，不是千问在线结果。",
                "evidence": _evidence(script["evidence"]),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "id": script["id"],
        "title": script["title"],
        "duration_s": script["duration_s"],
        "fire_xyz": script["fire_xyz"],
        "videos": videos,
        "detections": detection,
        "qwen": qwen,
    }


def build(root: Path = PACK) -> None:
    cameras = build_cameras()
    for script in SCRIPTS:
        _check_aim(script)
        _check_localization(cameras, script)
    root.mkdir(parents=True, exist_ok=True)
    documents = [_write_script(root, cameras, script) for script in SCRIPTS]
    manifest = {
        "id": "synthetic-classroom",
        "synthetic": True,
        "label": "合成数据",
        "note": NOTE,
        "fps": FPS,
        "width": IMAGE_W,
        "height": IMAGE_H,
        "epoch": "2026-11-15T00:00:00+00:00",
        "room": {
            "name": "演示教室",
            "scene_type": "classroom",
            "width_m": WIDTH_M,
            "depth_m": DEPTH_M,
            "height_m": HEIGHT_M,
            "combustibles": [
                {"name": "前排课桌", "polygon": [[3.35, 2.35], [4.65, 2.35], [4.65, 3.05], [3.35, 3.05]]},
                {"name": "配电箱", "polygon": [[6.20, 2.45], [6.75, 2.45], [6.75, 3.65], [6.20, 3.65]]},
            ],
        },
        "gimbal": {
            "p0": list(GIMBAL_P0),
            "yaw_deg": GIMBAL_YAW_DEG,
            "tilt_zero": GIMBAL_TILT_ZERO,
        },
        "cameras": [_camera_document(camera) for camera in cameras],
        "scripts": {item["id"]: item for item in documents},
    }
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "SYNTHETIC.txt").write_text(NOTE + "\n", encoding="utf-8")


def main() -> None:
    build()


if __name__ == "__main__":
    main()
