#!/usr/bin/env python3
"""Audit a YOLO dataset without modifying it."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import imagehash
import yaml
from PIL import Image, ImageOps

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@dataclass(frozen=True)
class ImageRecord:
    split: str
    image: Path
    sha256: str
    phash: int | None


@dataclass
class BKNode:
    value: int
    records: list[ImageRecord] = field(default_factory=list)
    children: dict[int, "BKNode"] = field(default_factory=dict)


class BKTree:
    def __init__(self) -> None:
        self.root: BKNode | None = None

    @staticmethod
    def distance(left: int, right: int) -> int:
        return (left ^ right).bit_count()

    def add(self, value: int, record: ImageRecord) -> None:
        if self.root is None:
            self.root = BKNode(value=value, records=[record])
            return
        node = self.root
        while True:
            distance = self.distance(value, node.value)
            if distance == 0:
                node.records.append(record)
                return
            child = node.children.get(distance)
            if child is None:
                node.children[distance] = BKNode(value=value, records=[record])
                return
            node = child

    def search(self, value: int, radius: int) -> Iterable[tuple[int, ImageRecord]]:
        if self.root is None:
            return []
        results: list[tuple[int, ImageRecord]] = []
        stack = [self.root]
        while stack:
            node = stack.pop()
            distance = self.distance(value, node.value)
            if distance <= radius:
                results.extend((distance, record) for record in node.records)
            low, high = distance - radius, distance + radius
            stack.extend(
                child
                for edge, child in node.children.items()
                if low <= edge <= high
            )
        return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True, help="YOLO dataset YAML.")
    parser.add_argument("--output", type=Path, required=True, help="JSON audit report.")
    parser.add_argument(
        "--phash-threshold",
        type=int,
        default=None,
        help="Optional cross-split perceptual-hash distance, usually 4.",
    )
    parser.add_argument(
        "--max-near-duplicate-pairs",
        type=int,
        default=2000,
        help="Cap report size without stopping the scan.",
    )
    return parser.parse_args()


def load_config(data_file: Path) -> tuple[dict[str, Path], dict[int, str]]:
    config = yaml.safe_load(data_file.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("Dataset YAML must be a mapping")
    root = Path(config.get("path", data_file.parent))
    if not root.is_absolute():
        root = (data_file.parent / root).resolve()
    splits: dict[str, Path] = {}
    for split in ("train", "val", "test"):
        value = config.get(split)
        if not isinstance(value, str):
            raise ValueError(f"Dataset YAML is missing a string '{split}' path")
        path = Path(value)
        splits[split] = path.resolve() if path.is_absolute() else (root / path).resolve()
    raw_names = config.get("names")
    if isinstance(raw_names, list):
        names = {index: str(name).lower() for index, name in enumerate(raw_names)}
    elif isinstance(raw_names, dict):
        names = {int(index): str(name).lower() for index, name in raw_names.items()}
    else:
        raise ValueError("Dataset YAML must define class names")
    return splits, names


def label_path(image_path: Path) -> Path:
    parts = list(image_path.parts)
    lower_parts = [part.lower() for part in parts]
    try:
        reverse_index = lower_parts[::-1].index("images")
    except ValueError as exc:
        raise ValueError(f"Image path has no images directory: {image_path}") from exc
    index = len(parts) - 1 - reverse_index
    parts[index] = "labels"
    return Path(*parts).with_suffix(".txt")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_label(
    path: Path,
    names: dict[int, str],
    errors: list[str],
    warnings: list[str],
) -> Counter[int]:
    counts = Counter[int]()
    if not path.exists():
        errors.append(f"missing label: {path}")
        return counts
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as exc:
        errors.append(f"unreadable label: {path}: {exc}")
        return counts
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        fields = line.split()
        if len(fields) != 5:
            errors.append(f"bad field count: {path}:{line_number}")
            continue
        try:
            class_id = int(fields[0])
            x, y, width, height = (float(value) for value in fields[1:])
        except ValueError:
            errors.append(f"non-numeric label: {path}:{line_number}")
            continue
        if class_id not in names:
            errors.append(f"unknown class {class_id}: {path}:{line_number}")
            continue
        if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < width <= 1 and 0 < height <= 1):
            errors.append(f"non-normalized box: {path}:{line_number}")
            continue
        x1, y1, x2, y2 = x - width / 2, y - height / 2, x + width / 2, y + height / 2
        if min(x1, y1) < -1e-6 or max(x2, y2) > 1 + 1e-6:
            warnings.append(f"box crosses image edge: {path}:{line_number}")
        counts[class_id] += 1
    return counts


def main() -> int:
    args = parse_args()
    if args.phash_threshold is not None and not (0 <= args.phash_threshold <= 16):
        raise SystemExit("--phash-threshold must be between 0 and 16")
    data_file = args.data.expanduser().resolve()
    splits, names = load_config(data_file)
    errors: list[str] = []
    warnings: list[str] = []
    records: list[ImageRecord] = []
    split_summary: dict[str, dict[str, object]] = {}

    for split, image_dir in splits.items():
        images = sorted(
            path
            for path in image_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )
        if not images:
            errors.append(f"no images in {split}: {image_dir}")
        object_counts = Counter[int]()
        background_images = 0
        resolutions = Counter[str]()
        for image_path in images:
            phash_value: int | None = None
            try:
                with Image.open(image_path) as opened:
                    opened.verify()
                with Image.open(image_path) as opened:
                    image = ImageOps.exif_transpose(opened).convert("RGB")
                    resolutions[f"{image.width}x{image.height}"] += 1
                    if args.phash_threshold is not None:
                        phash_value = int(str(imagehash.phash(image)), 16)
            except Exception as exc:  # noqa: BLE001 - Pillow raises many decoder types
                errors.append(f"bad image: {image_path}: {exc}")
                continue
            label_counts = parse_label(label_path(image_path), names, errors, warnings)
            object_counts.update(label_counts)
            if not label_counts:
                background_images += 1
            records.append(
                ImageRecord(
                    split=split,
                    image=image_path,
                    sha256=sha256_file(image_path),
                    phash=phash_value,
                )
            )
        split_summary[split] = {
            "image_directory": str(image_dir),
            "images": len(images),
            "background_images": background_images,
            "objects": {names[index]: object_counts[index] for index in sorted(names)},
            "top_resolutions": resolutions.most_common(10),
        }
        print(
            f"Audited {split}: {len(images):,} images, "
            f"{background_images:,} backgrounds, {sum(object_counts.values()):,} objects"
        )

    by_sha: dict[str, list[ImageRecord]] = defaultdict(list)
    for record in records:
        by_sha[record.sha256].append(record)
    exact_cross_split: list[dict[str, object]] = []
    for digest, group in by_sha.items():
        if len({record.split for record in group}) > 1:
            exact_cross_split.append(
                {
                    "sha256": digest,
                    "items": [
                        {"split": record.split, "image": str(record.image)}
                        for record in group
                    ],
                }
            )

    near_cross_split: list[dict[str, object]] = []
    near_pair_count = 0
    if args.phash_threshold is not None:
        tree = BKTree()
        seen_pairs: set[tuple[str, str]] = set()
        for record in records:
            assert record.phash is not None
            for distance, other in tree.search(record.phash, args.phash_threshold):
                if record.split == other.split:
                    continue
                pair = tuple(sorted((str(record.image), str(other.image))))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                near_pair_count += 1
                if len(near_cross_split) < args.max_near_duplicate_pairs:
                    near_cross_split.append(
                        {
                            "distance": distance,
                            "left": {"split": other.split, "image": str(other.image)},
                            "right": {"split": record.split, "image": str(record.image)},
                        }
                    )
            tree.add(record.phash, record)

    if exact_cross_split:
        errors.append(
            f"found {len(exact_cross_split)} exact duplicate groups across splits"
        )
    if near_pair_count:
        warnings.append(
            f"found {near_pair_count} possible perceptual duplicate pairs across splits; inspect them"
        )
    if names != {0: "fire", 1: "smoke"}:
        errors.append(f"expected names {{0: fire, 1: smoke}}, found {names}")

    report = {
        "data_yaml": str(data_file),
        "class_names": names,
        "splits": split_summary,
        "total_images": len(records),
        "exact_cross_split_duplicate_groups": exact_cross_split,
        "near_cross_split_duplicate_pair_count": near_pair_count,
        "near_cross_split_duplicate_pairs_reported": near_cross_split,
        "phash_threshold": args.phash_threshold,
        "errors": errors,
        "warnings": warnings,
        "passed_structural_checks": not errors,
    }
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Audit report: {output}")
    if errors:
        print(f"FAILED with {len(errors)} error(s). Stop before training.")
        return 1
    print(f"PASSED with {len(warnings)} warning(s). Review warnings before training.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
