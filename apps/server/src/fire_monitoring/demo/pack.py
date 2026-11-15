from __future__ import annotations

import json
from pathlib import Path


def load_pack(path: str | Path) -> dict:
    root = Path(path)
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"录像包缺少 manifest.json：{root}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["root"] = root
    for key in ("fps", "width", "height", "epoch", "room", "gimbal", "cameras", "scripts"):
        if key not in manifest:
            raise RuntimeError(f"录像单缺少 {key}")
    if len(manifest["cameras"]) != 4:
        raise RuntimeError("演示录像需要四路相机")
    for camera in manifest["cameras"]:
        if len(camera["landmarks"]) < 4:
            raise RuntimeError(f"{camera['name']} 的控制点不足")
    for script in manifest["scripts"].values():
        for relative in script["videos"].values():
            if not (root / relative).is_file():
                raise RuntimeError(f"缺少录像 {relative}")
        if not (root / script["detections"]).is_file():
            raise RuntimeError(f"缺少检测框文件 {script['detections']}")
        if not (root / script["qwen"]).is_file():
            raise RuntimeError(f"缺少千问缓存 {script['qwen']}")
    return manifest


def load_json(pack: dict, relative: str) -> dict:
    return json.loads((pack["root"] / relative).read_text(encoding="utf-8"))
