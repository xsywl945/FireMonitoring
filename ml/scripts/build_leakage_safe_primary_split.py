#!/usr/bin/env python3
"""Build the primary split while isolating IFireSmoke validation and test images.

The combined manifest keeps both datasets' official splits for traceability. This
script creates the split used for early stopping and primary reporting:

* train: D-Fire train plus IFireSmoke train, excluding perceptual matches to
  protected validation/test images;
* val: IFireSmoke val, excluding perceptual matches to IFireSmoke test;
* test: the unchanged IFireSmoke test split.

Source data and the combined dataset are never modified.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import imagehash
import yaml
from PIL import Image


@dataclass(frozen=True)
class Sample:
    source: str
    source_split: str
    image: Path
    label: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phash-threshold", type=int, default=4)
    parser.add_argument("--link", action="store_true")
    return parser.parse_args()


def load_manifest(path: Path) -> list[Sample]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    samples = [
        Sample(
            source=row["source"],
            source_split=row["split"],
            image=Path(row["target_image"]),
            label=Path(row["target_label"]),
        )
        for row in rows
    ]
    for sample in samples:
        if not sample.image.is_file() or not sample.label.is_file():
            raise FileNotFoundError(f"manifest target is missing: {sample}")
    return samples


def perceptual_hash(path: Path) -> int:
    with Image.open(path) as image:
        return int(str(imagehash.phash(image)), 16)


def nearest_match(
    value: int,
    protected: list[tuple[int, Sample]],
    threshold: int,
) -> tuple[int, Sample] | None:
    best: tuple[int, Sample] | None = None
    for other_value, other in protected:
        distance = (value ^ other_value).bit_count()
        if distance <= threshold and (best is None or distance < best[0]):
            best = (distance, other)
            if distance == 0:
                break
    return best


def materialize(
    sample: Sample, output: Path, split: str, *, link: bool
) -> tuple[Path, Path]:
    image_target = output / "images" / split / sample.image.name
    label_target = output / "labels" / split / sample.label.name
    image_target.parent.mkdir(parents=True, exist_ok=True)
    label_target.parent.mkdir(parents=True, exist_ok=True)
    if image_target.exists() or label_target.exists():
        raise FileExistsError(f"refusing to overwrite generated sample: {image_target}")
    for source, target in ((sample.image, image_target), (sample.label, label_target)):
        if link:
            try:
                target.hardlink_to(source)
                continue
            except OSError:
                pass
        shutil.copy2(source, target)
    return image_target, label_target


def removal_record(
    sample: Sample,
    sample_hash: int,
    match: tuple[int, Sample],
) -> dict[str, object]:
    distance, protected = match
    return {
        "source": sample.source,
        "source_split": sample.source_split,
        "image": str(sample.image),
        "phash": f"{sample_hash:016x}",
        "distance": distance,
        "protected_source": protected.source,
        "protected_split": protected.source_split,
        "protected_image": str(protected.image),
    }


def main() -> int:
    args = parse_args()
    if not 0 <= args.phash_threshold <= 16:
        print("ERROR: --phash-threshold must be between 0 and 16", file=sys.stderr)
        return 2
    manifest = args.manifest.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if not manifest.is_file():
        print(f"ERROR: manifest does not exist: {manifest}", file=sys.stderr)
        return 2
    if output.exists() and any(output.iterdir()):
        print(f"ERROR: output is not empty: {output}", file=sys.stderr)
        return 2
    output.mkdir(parents=True, exist_ok=True)

    samples = load_manifest(manifest)
    train_candidates = sorted(
        (sample for sample in samples if sample.source_split == "train"),
        key=lambda sample: str(sample.image),
    )
    val_candidates = sorted(
        (
            sample
            for sample in samples
            if sample.source == "ifiresmoke" and sample.source_split == "val"
        ),
        key=lambda sample: str(sample.image),
    )
    test_samples = sorted(
        (
            sample
            for sample in samples
            if sample.source == "ifiresmoke" and sample.source_split == "test"
        ),
        key=lambda sample: str(sample.image),
    )
    if len(test_samples) != 500 or len(val_candidates) != 500:
        raise ValueError(
            "expected 500 IFireSmoke validation and 500 test images before isolation"
        )

    test_hashes = [(perceptual_hash(sample.image), sample) for sample in test_samples]
    kept_val: list[Sample] = []
    kept_val_hashes: list[tuple[int, Sample]] = []
    removals: list[dict[str, object]] = []
    for sample in val_candidates:
        value = perceptual_hash(sample.image)
        match = nearest_match(value, test_hashes, args.phash_threshold)
        if match is None:
            kept_val.append(sample)
            kept_val_hashes.append((value, sample))
        else:
            removals.append(removal_record(sample, value, match))

    protected = [*test_hashes, *kept_val_hashes]
    kept_train: list[Sample] = []
    for index, sample in enumerate(train_candidates, start=1):
        value = perceptual_hash(sample.image)
        match = nearest_match(value, protected, args.phash_threshold)
        if match is None:
            kept_train.append(sample)
        else:
            removals.append(removal_record(sample, value, match))
        if index % 1000 == 0:
            print(f"Checked {index:,}/{len(train_candidates):,} training images")

    output_manifest: list[dict[str, str]] = []
    for target_split, split_samples in (
        ("train", kept_train),
        ("val", kept_val),
        ("test", test_samples),
    ):
        for sample in split_samples:
            image_target, label_target = materialize(
                sample, output, target_split, link=args.link
            )
            output_manifest.append(
                {
                    "source": sample.source,
                    "source_split": sample.source_split,
                    "target_split": target_split,
                    "source_image": str(sample.image),
                    "source_label": str(sample.label),
                    "target_image": str(image_target),
                    "target_label": str(label_target),
                }
            )

    data = {
        "path": output.as_posix(),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "names": {0: "fire", 1: "smoke"},
    }
    (output / "primary_fire_smoke_v1.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (output / "leakage_removals.json").write_text(
        json.dumps(removals, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (output / "manifest.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output_manifest[0]))
        writer.writeheader()
        writer.writerows(output_manifest)
    kept_by_source = Counter(sample.source for sample in kept_train)
    removed_by_source_split = Counter(
        (str(item["source"]), str(item["source_split"])) for item in removals
    )
    summary = {
        "phash_threshold": args.phash_threshold,
        "train_images": len(kept_train),
        "val_images": len(kept_val),
        "test_images": len(test_samples),
        "train_images_by_source": dict(kept_by_source),
        "removed_images": len(removals),
        "removed_images_by_source_split": {
            f"{source}/{split}": count
            for (source, split), count in sorted(removed_by_source_split.items())
        },
        "test_is_unchanged_ifiresmoke": True,
        "dfire_val_test_used_in_primary": False,
    }
    (output / "primary_split_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Primary data YAML: {output / 'primary_fire_smoke_v1.yaml'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
