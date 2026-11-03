from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
from collections import Counter
from pathlib import Path

import imagehash
import yaml
from PIL import Image

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def sha256_file(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def scene_group(source: str, stem: str) -> tuple[str, str]:
    stem = stem.split(".rf.")[0]
    video = re.match(r"(FireDataV[0-9]+_[0-9]+)_", stem)
    if video:
        return f"{source}:{video[1]}", "video_filename"
    if source == "dfire" and stem.startswith(("AoF", "PublicDataset")):
        prefix = re.match(r"[A-Za-z]+", stem)[0]
        return f"{source}:{prefix}", "conservative_collection"
    stem = re.sub(r"(?:_jpg|_png)$", "", stem)
    return f"{source}:{stem}", "image_identity_phash_only"


def map_label(
    label_path: Path | None,
    class_map: dict[int, int],
    *,
    allow_repairs: bool,
) -> tuple[str, tuple[int, int], list[dict[str, object]]]:
    if label_path is None or not label_path.exists():
        return "", (0, 0), []
    mapped_lines: list[str] = []
    counts = Counter[int]()
    repairs: list[dict[str, object]] = []
    for line_number, raw_line in enumerate(
        label_path.read_text(encoding="utf-8-sig").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line:
            continue
        fields = line.split()
        if len(fields) != 5:
            raise ValueError(
                f"{label_path}:{line_number}: expected 5 YOLO fields, got {len(fields)}"
            )
        try:
            source_class = int(fields[0])
            x, y, width, height = (float(value) for value in fields[1:])
        except ValueError as exc:
            raise ValueError(f"{label_path}:{line_number}: non-numeric label") from exc
        if source_class not in class_map:
            raise ValueError(
                f"{label_path}:{line_number}: unexpected source class {source_class}"
            )
        values = (x, y, width, height)
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"{label_path}:{line_number}: non-finite coordinates")
        target_class = class_map[source_class]
        original = {"x": x, "y": y, "width": width, "height": height}
        if width <= 0 or height <= 0:
            if not allow_repairs:
                raise ValueError(
                    f"{label_path}:{line_number}: non-positive box dimensions"
                )
            repairs.append(
                {
                    "line_number": line_number,
                    "action": "drop_degenerate_box",
                    "source_class": source_class,
                    "target_class": target_class,
                    "original": original,
                }
            )
            continue
        left = x - width / 2
        top = y - height / 2
        right = x + width / 2
        bottom = y + height / 2
        needs_clip = not (
            0 <= x <= 1
            and 0 <= y <= 1
            and width <= 1
            and height <= 1
            and left >= 0
            and top >= 0
            and right <= 1
            and bottom <= 1
        )
        if needs_clip:
            if not allow_repairs:
                raise ValueError(
                    f"{label_path}:{line_number}: coordinates outside normalized YOLO range"
                )
            excess = max(0.0, -left, -top, right - 1, bottom - 1)
            if excess > 0.1:
                raise ValueError(
                    f"{label_path}:{line_number}: box exceeds image by {excess:.6f}, "
                    "above the controlled repair limit"
                )
            left = max(0.0, left)
            top = max(0.0, top)
            right = min(1.0, right)
            bottom = min(1.0, bottom)
            if right <= left or bottom <= top:
                raise ValueError(
                    f"{label_path}:{line_number}: box has no area inside the image"
                )
            x = (left + right) / 2
            y = (top + bottom) / 2
            width = right - left
            height = bottom - top
            repairs.append(
                {
                    "line_number": line_number,
                    "action": "clip_box_to_image",
                    "source_class": source_class,
                    "target_class": target_class,
                    "original": original,
                    "repaired": {
                        "x": x,
                        "y": y,
                        "width": width,
                        "height": height,
                    },
                }
            )
        counts[target_class] += 1
        mapped_lines.append(
            " ".join(
                [
                    str(target_class),
                    *[f"{value:.8f}" for value in (x, y, width, height)],
                ]
            )
        )
    mapped = "\n".join(mapped_lines)
    if mapped:
        mapped += "\n"
    return mapped, (counts[0], counts[1]), repairs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--link", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = json.loads(args.sources.read_text(encoding="utf-8"))
    rows, repairs = [], []
    for spec in sources:
        root = Path(spec["root"])
        names = spec["names"]
        if names:
            declared = yaml.safe_load(
                (root / spec["yaml"]).read_text(encoding="utf-8")
            )["names"]
            if isinstance(declared, dict):
                declared = [declared[k] for k in sorted(declared, key=int)]
            declared = [name.lower() for name in declared]
            if declared != names:
                raise ValueError(
                    f"{spec['name']}: declared classes {declared} != {names}"
                )
        class_map = {i: ["fire", "smoke"].index(name) for i, name in enumerate(names)}
        metadata = {}
        if "metadata" in spec:
            with (root / spec["metadata"]).open(encoding="utf-8", newline="") as handle:
                metadata = {r["filename"]: r for r in csv.DictReader(handle)}
        for split, directory in spec["splits"].items():
            image_dir = root / directory / "images"
            images = sorted(
                p for p in image_dir.rglob("*") if p.suffix.lower() in IMAGE_EXTENSIONS
            )
            if not images:
                raise ValueError(f"No images: {image_dir}")
            for image in images:
                source_label = (
                    root
                    / directory
                    / "labels"
                    / image.relative_to(image_dir).with_suffix(".txt")
                )
                if not spec["background"] and not source_label.is_file():
                    raise FileNotFoundError(source_label)
                text, counts, fixes = map_label(
                    None if spec["background"] else source_label,
                    class_map,
                    allow_repairs=True,
                )
                digest = sha256_file(image)
                with Image.open(image) as opened:
                    opened.load()
                    width, height = opened.size
                    phash = str(imagehash.phash(opened))
                name = (
                    f"{spec['name']}__{image.stem}__{digest[:12]}{image.suffix.lower()}"
                )
                target = output / "images" / split / name
                target.parent.mkdir(parents=True, exist_ok=True)
                if args.link:
                    os.link(image, target)
                else:
                    shutil.copy2(image, target)
                label = output / "labels" / split / Path(name).with_suffix(".txt")
                label.parent.mkdir(parents=True, exist_ok=True)
                label.write_text(text, encoding="utf-8")
                group, method = scene_group(spec["name"], image.stem)
                extra = metadata.get(image.name, {})
                rows.append(
                    dict(
                        source=spec["name"],
                        split=split,
                        source_image=str(image),
                        source_label=str(source_label),
                        target_image=str(target),
                        target_label=str(label),
                        sha256=digest,
                        label_sha256=sha256_file(label),
                        phash=phash,
                        width=width,
                        height=height,
                        fire_objects=counts[0],
                        smoke_objects=counts[1],
                        group=extra.get("group", group),
                        group_method=extra.get("group_method", method),
                        source_url=extra.get("source_url", spec["url"]),
                        license=extra.get("license", spec["license"]),
                        selection=extra.get("selection", "official_dataset"),
                    )
                )
                repairs.extend(
                    dict(source=spec["name"], image=str(image), **fix) for fix in fixes
                )
        print(
            f"Collected {spec['name']}: {sum(r['source'] == spec['name'] for r in rows)}",
            flush=True,
        )
    with (output / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (output / "source_label_repairs.json").write_text(
        json.dumps(repairs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    shutil.copy2(args.sources, output / "sources.json")
    print(
        json.dumps(
            {
                "images": len(rows),
                "repairs": len(repairs),
                "manifest_sha256": sha256_file(output / "manifest.csv"),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
