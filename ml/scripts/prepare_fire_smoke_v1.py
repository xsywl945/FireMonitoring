#!/usr/bin/env python3
"""Merge official D-Fire and IFireSmoke splits into a safe two-class dataset.

The source datasets use opposite class identifiers:

* D-Fire: 0=smoke, 1=fire
* IFireSmoke: 0=fire, 1=smoke

The generated dataset always uses 0=fire and 1=smoke. Source files are never
modified. Exact duplicate images are kept in only one combined split, with the
priority test > val > train to prevent exact train/test leakage.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SPLIT_PRIORITY = {"train": 1, "val": 2, "test": 3}


@dataclass(frozen=True)
class SourceSpec:
    name: str
    root: Path
    split_aliases: dict[str, tuple[str, ...]]
    expected_names: tuple[str, str]
    class_map: dict[int, int]
    expected_total_images: int
    expected_background_images: int


@dataclass(frozen=True)
class Example:
    source: str
    split: str
    image_path: Path
    label_path: Path | None
    image_sha256: str
    mapped_label: str
    object_counts: tuple[int, int]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dfire-root",
        type=Path,
        required=True,
        help="Directory containing D-Fire train/val/test folders.",
    )
    parser.add_argument(
        "--ifiresmoke-root",
        type=Path,
        required=True,
        help="Directory containing IFireSmoke train/valid/test folders.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="A new, empty output directory. Existing data is never overwritten.",
    )
    parser.add_argument(
        "--link",
        action="store_true",
        help="Use hard links for images when possible; otherwise copy files.",
    )
    return parser.parse_args()


def normalize_name(value: object) -> str:
    return str(value).strip().lower().replace("_", "").replace("-", "")


def find_dataset_root(candidate: Path, train_aliases: tuple[str, ...]) -> Path:
    candidate = candidate.expanduser().resolve()
    if not candidate.is_dir():
        raise ValueError(f"Dataset root is not a directory: {candidate}")
    aliases = {alias.lower() for alias in train_aliases}

    def has_train(directory: Path) -> bool:
        return any(
            child.is_dir() and child.name.lower() in aliases
            for child in directory.iterdir()
        )

    if has_train(candidate):
        return candidate
    for child in sorted(path for path in candidate.iterdir() if path.is_dir()):
        if has_train(child):
            return child
        for grandchild in sorted(path for path in child.iterdir() if path.is_dir()):
            if has_train(grandchild):
                return grandchild
    raise ValueError(
        f"Could not find a train folder within two levels under {candidate}"
    )


def find_split(root: Path, aliases: tuple[str, ...]) -> Path:
    children = {child.name.lower(): child for child in root.iterdir() if child.is_dir()}
    for alias in aliases:
        found = children.get(alias.lower())
        if found is not None:
            return found
    raise ValueError(f"None of split folders {aliases} exists under {root}")


def find_images_dir(split_dir: Path) -> Path:
    for child in split_dir.iterdir():
        if child.is_dir() and child.name.lower() in {"images", "image"}:
            return child
    raise ValueError(f"No images directory under {split_dir}")


def find_labels_dir(split_dir: Path) -> Path | None:
    for child in split_dir.iterdir():
        if child.is_dir() and child.name.lower() in {"labels", "label"}:
            return child
    return None


def read_declared_names(root: Path) -> tuple[str, ...] | None:
    yaml_files = sorted([*root.glob("*.yaml"), *root.glob("*.yml")])
    for yaml_file in yaml_files:
        try:
            document = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError):
            continue
        if not isinstance(document, dict) or "names" not in document:
            continue
        raw_names = document["names"]
        if isinstance(raw_names, list):
            return tuple(normalize_name(name) for name in raw_names)
        if isinstance(raw_names, dict):
            return tuple(
                normalize_name(raw_names[index])
                for index in sorted(raw_names, key=lambda value: int(value))
            )
    return None


def verify_declared_names(spec: SourceSpec) -> None:
    observed = read_declared_names(spec.root)
    expected = tuple(normalize_name(name) for name in spec.expected_names)
    if observed is None:
        print(
            f"WARNING: {spec.name} has no readable data YAML; using documented class "
            f"order {spec.expected_names}.",
            file=sys.stderr,
        )
        return
    if observed != expected:
        raise ValueError(
            f"{spec.name} class order is {observed}, expected {expected}. "
            "Stop and inspect the downloaded dataset instead of guessing."
        )
    print(f"Verified {spec.name} source classes: {observed}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def map_label(label_path: Path | None, class_map: dict[int, int]) -> tuple[str, tuple[int, int]]:
    if label_path is None or not label_path.exists():
        return "", (0, 0)
    mapped_lines: list[str] = []
    counts = Counter[int]()
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
        if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < width <= 1 and 0 < height <= 1):
            raise ValueError(
                f"{label_path}:{line_number}: coordinates outside normalized YOLO range"
            )
        target_class = class_map[source_class]
        counts[target_class] += 1
        mapped_lines.append(
            " ".join([str(target_class), *[f"{value:.8f}" for value in (x, y, width, height)]])
        )
    mapped = "\n".join(mapped_lines)
    if mapped:
        mapped += "\n"
    return mapped, (counts[0], counts[1])


def collect_examples(spec: SourceSpec) -> tuple[list[Example], dict[str, object]]:
    examples: list[Example] = []
    split_images: dict[str, int] = {}
    missing_label_files = 0
    empty_label_files = 0
    for target_split in ("train", "val", "test"):
        split_dir = find_split(spec.root, spec.split_aliases[target_split])
        image_dir = find_images_dir(split_dir)
        labels_dir = find_labels_dir(split_dir)
        images = sorted(
            path
            for path in image_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )
        if not images:
            raise ValueError(f"No images found in {image_dir}")
        split_images[target_split] = len(images)
        for image_path in images:
            relative_label = image_path.relative_to(image_dir).with_suffix(".txt")
            label_path = labels_dir / relative_label if labels_dir else None
            if label_path is None or not label_path.exists():
                missing_label_files += 1
            elif not label_path.read_text(encoding="utf-8-sig").strip():
                empty_label_files += 1
            mapped_label, object_counts = map_label(label_path, spec.class_map)
            examples.append(
                Example(
                    source=spec.name,
                    split=target_split,
                    image_path=image_path,
                    label_path=label_path if label_path and label_path.exists() else None,
                    image_sha256=sha256_file(image_path),
                    mapped_label=mapped_label,
                    object_counts=object_counts,
                )
            )
        print(f"Collected {len(images):,} {spec.name} {target_split} images")
    background_images = sum(not any(example.object_counts) for example in examples)
    if len(examples) != spec.expected_total_images:
        raise ValueError(
            f"{spec.name} contains {len(examples):,} images, expected the documented "
            f"{spec.expected_total_images:,}; the download may be incomplete or a different version"
        )
    if background_images != spec.expected_background_images:
        raise ValueError(
            f"{spec.name} contains {background_images:,} images without objects, expected "
            f"{spec.expected_background_images:,}; missing labels may be hiding positive samples"
        )
    integrity = {
        "split_images": split_images,
        "total_images": len(examples),
        "background_images": background_images,
        "missing_source_label_files": missing_label_files,
        "empty_source_label_files": empty_label_files,
    }
    print(f"Verified {spec.name} source integrity: {integrity}")
    return examples, integrity


def choose_combined_examples(
    examples: Iterable[Example],
) -> tuple[list[Example], list[dict[str, object]], list[dict[str, object]]]:
    by_hash: dict[str, list[Example]] = defaultdict(list)
    for example in examples:
        by_hash[example.image_sha256].append(example)

    kept: list[Example] = []
    duplicates: list[dict[str, object]] = []
    conflicts: list[dict[str, object]] = []
    for digest, group in sorted(by_hash.items()):
        ordered = sorted(
            group,
            key=lambda item: (
                -SPLIT_PRIORITY[item.split],
                item.source,
                item.image_path.as_posix(),
            ),
        )
        image_winner = ordered[0]
        non_empty_class_sets = {
            frozenset(index for index, count in enumerate(item.object_counts) if count)
            for item in group
            if sum(item.object_counts)
        }
        has_disjoint_annotations = any(
            left.isdisjoint(right)
            for left in non_empty_class_sets
            for right in non_empty_class_sets
            if left != right
        )
        if has_disjoint_annotations:
            conflicts.append(
                {
                    "sha256": digest,
                    "reason": "identical pixels have disjoint non-empty class annotations",
                    "items": [
                        {
                            "source": item.source,
                            "split": item.split,
                            "image": str(item.image_path),
                            "label": str(item.label_path or ""),
                            "fire_objects": item.object_counts[0],
                            "smoke_objects": item.object_counts[1],
                        }
                        for item in ordered
                    ],
                }
            )
            continue
        annotation_winner = sorted(
            group,
            key=lambda item: (
                -sum(item.object_counts),
                item.source,
                item.image_path.as_posix(),
            ),
        )[0]
        winner = Example(
            source=image_winner.source,
            split=image_winner.split,
            image_path=image_winner.image_path,
            label_path=annotation_winner.label_path,
            image_sha256=image_winner.image_sha256,
            mapped_label=annotation_winner.mapped_label,
            object_counts=annotation_winner.object_counts,
        )
        kept.append(winner)
        if len(group) > 1:
            duplicates.append(
                {
                    "sha256": digest,
                    "kept": {
                        "source": winner.source,
                        "split": winner.split,
                        "path": str(winner.image_path),
                    },
                    "annotation_selected": {
                        "source": annotation_winner.source,
                        "split": annotation_winner.split,
                        "path": str(annotation_winner.label_path or ""),
                    },
                    "removed": [
                        {
                            "source": item.source,
                            "split": item.split,
                            "path": str(item.image_path),
                        }
                        for item in ordered[1:]
                    ],
                }
            )
    return (
        sorted(kept, key=lambda item: (item.split, item.source, str(item.image_path))),
        duplicates,
        conflicts,
    )


def target_name(example: Example) -> str:
    safe_stem = "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in example.image_path.stem
    )
    return (
        f"{example.source}__{safe_stem}__{example.image_sha256[:10]}"
        f"{example.image_path.suffix.lower()}"
    )


def materialize(example: Example, root: Path, *, link: bool) -> tuple[Path, Path]:
    image_dir = root / "images" / example.split
    label_dir = root / "labels" / example.split
    image_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)
    image_target = image_dir / target_name(example)
    label_target = label_dir / f"{image_target.stem}.txt"
    if image_target.exists() or label_target.exists():
        raise FileExistsError(f"Refusing to overwrite generated sample {image_target}")
    if link:
        try:
            image_target.hardlink_to(example.image_path)
        except OSError:
            shutil.copy2(example.image_path, image_target)
    else:
        shutil.copy2(example.image_path, image_target)
    label_target.write_text(example.mapped_label, encoding="utf-8")
    return image_target, label_target


def write_data_yaml(path: Path, root: Path, *, test_only: bool = False) -> None:
    document = {
        "path": root.resolve().as_posix(),
        "train": "images/test" if test_only else "images/train",
        "val": "images/test" if test_only else "images/val",
        "test": "images/test",
        "names": {0: "fire", 1: "smoke"},
    }
    path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def main() -> int:
    args = parse_args()
    output = args.output.expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        print(
            f"ERROR: output is not empty: {output}\n"
            "Choose a new versioned output directory; this script never deletes old data.",
            file=sys.stderr,
        )
        return 2
    output.mkdir(parents=True, exist_ok=True)

    try:
        dfire_root = find_dataset_root(
            args.dfire_root, ("train", "training", "train_set")
        )
        ifire_root = find_dataset_root(
            args.ifiresmoke_root, ("train", "training", "train_set")
        )
        specs = [
            SourceSpec(
                name="dfire",
                root=dfire_root,
                split_aliases={
                    "train": ("train", "training", "train_set"),
                    "val": ("val", "valid", "validation", "validation_set"),
                    "test": ("test", "testing", "test_set"),
                },
                expected_names=("smoke", "fire"),
                class_map={0: 1, 1: 0},
                expected_total_images=21_527,
                expected_background_images=9_838,
            ),
            SourceSpec(
                name="ifiresmoke",
                root=ifire_root,
                split_aliases={
                    "train": ("train", "training", "train_set"),
                    "val": ("valid", "val", "validation", "validation_set"),
                    "test": ("test", "testing", "test_set"),
                },
                expected_names=("fire", "smoke"),
                class_map={0: 0, 1: 1},
                expected_total_images=5_000,
                expected_background_images=0,
            ),
        ]
        all_examples: list[Example] = []
        by_source: dict[str, list[Example]] = {}
        source_integrity: dict[str, dict[str, object]] = {}
        for spec in specs:
            verify_declared_names(spec)
            collected, integrity = collect_examples(spec)
            by_source[spec.name] = collected
            source_integrity[spec.name] = integrity
            all_examples.extend(collected)
        combined, duplicates, conflicts = choose_combined_examples(all_examples)
        if conflicts:
            conflict_path = output / "exact_duplicate_annotation_conflicts.json"
            conflict_path.write_text(
                json.dumps(conflicts, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            raise ValueError(
                f"found {len(conflicts)} exact duplicate annotation conflict(s); "
                f"inspect {conflict_path} and clean the source data"
            )

        manifest_rows: list[dict[str, object]] = []
        split_images = Counter[str]()
        split_objects: dict[str, Counter[int]] = defaultdict(Counter)
        for example in combined:
            image_target, label_target = materialize(example, output, link=args.link)
            split_images[example.split] += 1
            split_objects[example.split][0] += example.object_counts[0]
            split_objects[example.split][1] += example.object_counts[1]
            manifest_rows.append(
                {
                    "source": example.source,
                    "split": example.split,
                    "source_image": str(example.image_path),
                    "source_label": str(example.label_path or ""),
                    "target_image": str(image_target),
                    "target_label": str(label_target),
                    "sha256": example.image_sha256,
                    "fire_objects": example.object_counts[0],
                    "smoke_objects": example.object_counts[1],
                }
            )

        write_data_yaml(output / "fire_smoke_v1.yaml", output)

        eval_counts: dict[str, int] = {}
        for source_name, source_examples in by_source.items():
            eval_root = output / "eval" / source_name
            test_examples = [item for item in source_examples if item.split == "test"]
            for example in test_examples:
                materialize(example, eval_root, link=args.link)
            write_data_yaml(
                output / f"{source_name}_test.yaml", eval_root, test_only=True
            )
            eval_counts[source_name] = len(test_examples)

        manifest_path = output / "manifest.csv"
        with manifest_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(manifest_rows[0]))
            writer.writeheader()
            writer.writerows(manifest_rows)
        (output / "exact_duplicates_removed.json").write_text(
            json.dumps(duplicates, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        summary = {
            "class_names": {"0": "fire", "1": "smoke"},
            "source_roots": {spec.name: str(spec.root) for spec in specs},
            "source_integrity": source_integrity,
            "combined_images": dict(split_images),
            "combined_objects": {
                split: {
                    "fire": split_objects[split][0],
                    "smoke": split_objects[split][1],
                }
                for split in ("train", "val", "test")
            },
            "source_test_images": eval_counts,
            "exact_duplicate_groups_removed": len(duplicates),
            "link_mode_requested": bool(args.link),
        }
        (output / "prepare_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:  # noqa: BLE001 - present a beginner-friendly stop message
        print(f"ERROR: dataset preparation stopped: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Prepared dataset YAML: {output / 'fire_smoke_v1.yaml'}")
    print("Next: run audit_yolo_dataset.py and preview_yolo_dataset.py before training.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
