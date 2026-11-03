from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from audit_yolo_dataset import BKTree, ImageRecord
from prepare_fire_smoke_v1 import sha256_file


def read_rows(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--baseline-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phash-threshold", type=int, default=4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--background-fraction", type=float, default=0.125)
    parser.add_argument("--link", action="store_true")
    args = parser.parse_args()
    if not 0 <= args.phash_threshold <= 16 or not 0 < args.background_fraction < 1:
        parser.error("invalid phash threshold or background fraction")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    rows = read_rows(args.manifest)
    parents = list(range(len(rows)))

    def find(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left, right):
        parents[find(right)] = find(left)

    tree = BKTree()
    duplicate_parent = list(range(len(rows)))
    # Deduplication and scene grouping have different meanings: retain all distinct frames of a scene.
    duplicate_edges = []
    groups, exact = {}, {}
    for i, row in enumerate(rows):
        if row["group"] in groups:
            union(i, groups[row["group"]])
        groups[row["group"]] = i
        value = int(row["phash"], 16)
        matches = [
            int(record.image.name)
            for _, record in tree.search(value, args.phash_threshold)
        ]
        if row["sha256"] in exact:
            matches.append(exact[row["sha256"]])
        for j in matches:
            union(i, j)
            duplicate_edges.append((i, j))
        tree.add(value, ImageRecord(row["split"], Path(str(i)), row["sha256"], value))
        exact[row["sha256"]] = i
    scene_ids = [find(i) for i in range(len(rows))]
    parents = duplicate_parent
    for i, j in duplicate_edges:
        union(i, j)
    duplicates = defaultdict(list)
    for i in range(len(rows)):
        duplicates[find(i)].append(i)
    kept, removals = [], []
    for indices in duplicates.values():
        winner = min(
            indices,
            key=lambda i: (
                -int(rows[i]["fire_objects"]) - int(rows[i]["smoke_objects"]),
                rows[i]["sha256"],
                rows[i]["source_image"],
            ),
        )
        kept.append(winner)
        removals.extend(
            dict(
                image=rows[i]["source_image"],
                kept=rows[winner]["source_image"],
                reason="phash_component",
            )
            for i in indices
            if i != winner
        )
    baseline = read_rows(args.baseline_manifest)
    seen = {
        Path(r["target_image"]).name
        for r in baseline
        if r["target_split"] in {"train", "val"}
    }
    seen_ids = {n.rsplit("__", 1)[0] for n in seen}
    locked = {
        scene_ids[i]
        for i, row in enumerate(rows)
        if Path(row["target_image"]).name.rsplit("__", 1)[0] in seen_ids
    }
    components = defaultdict(list)
    for i in kept:
        components[scene_ids[i]].append(i)
    assignment = {}
    for component, indices in sorted(components.items()):
        identity = min(rows[i]["sha256"] for i in indices)
        draw = (
            int(hashlib.sha256(f"{args.seed}:{identity}".encode()).hexdigest()[:8], 16)
            / 2**32
        )
        assignment[component] = (
            "train"
            if component in locked or draw < 0.7
            else "val"
            if draw < 0.85
            else "test"
        )
    train_positive = sum(
        assignment[scene_ids[i]] == "train"
        and int(rows[i]["fire_objects"]) + int(rows[i]["smoke_objects"]) > 0
        for i in kept
    )
    backgrounds = [
        i
        for i in kept
        if assignment[scene_ids[i]] == "train"
        and int(rows[i]["fire_objects"]) + int(rows[i]["smoke_objects"]) == 0
    ]
    random.Random(args.seed).shuffle(backgrounds)
    budget = int(
        train_positive * args.background_fraction / (1 - args.background_fraction)
    )
    hard = [i for i in backgrounds if rows[i]["source"] == "negatives"]
    natural = [i for i in backgrounds if rows[i]["source"] != "negatives"]
    selected_backgrounds = set(hard[:budget] + natural[: max(0, budget - len(hard))])
    output_rows = []
    for i in kept:
        row = rows[i].copy()
        split = assignment[scene_ids[i]]
        if (
            split == "train"
            and not int(row["fire_objects"]) + int(row["smoke_objects"])
            and i not in selected_backgrounds
        ):
            removals.append(dict(image=row["source_image"], reason="background_budget"))
            continue
        for key, directory in (("target_image", "images"), ("target_label", "labels")):
            source = Path(row[key])
            target = output / directory / split / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            if args.link:
                os.link(source, target)
            else:
                shutil.copy2(source, target)
            row[key] = target.relative_to(output).as_posix()
        row.update(
            split=split,
            source_group=row["group"],
            group=f"scene-{scene_ids[i]}",
            baseline_exposed=str(scene_ids[i] in locked).lower(),
        )
        output_rows.append(row)
    with (output / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)
    for source in sorted({r["source"] for r in output_rows}):
        selected = [
            r["target_image"]
            for r in output_rows
            if r["source"] == source and r["split"] == "test"
        ]
        if selected:
            (output / f"{source}_test.txt").write_text(
                "".join(f"./{p}\n" for p in selected), encoding="utf-8"
            )
    config = dict(
        path=output.as_posix(),
        train="images/train",
        val="images/val",
        test="images/test",
        names={0: "fire", 1: "smoke"},
    )
    (output / "data.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )
    for source in sorted({r["source"] for r in output_rows if r["split"] == "test"}):
        (output / f"{source}_test.yaml").write_text(
            yaml.safe_dump(dict(config, test=f"{source}_test.txt"), sort_keys=False),
            encoding="utf-8",
        )
    summary = dict(
        images=dict(Counter(r["split"] for r in output_rows)),
        by_source=dict(Counter(f"{r['source']}/{r['split']}" for r in output_rows)),
        removed=len(removals),
        phash_threshold=args.phash_threshold,
        baseline_manifest_sha256=sha256_file(args.baseline_manifest),
        baseline_exposed_test=sum(
            r["split"] == "test" and r["baseline_exposed"] == "true"
            for r in output_rows
        ),
        train_background_fraction=len(selected_backgrounds)
        / (train_positive + len(selected_backgrounds)),
    )
    (output / "split_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (output / "removals.json").write_text(
        json.dumps(removals, indent=2), encoding="utf-8"
    )
    for name in (
        "sources.json",
        "source_label_repairs.json",
        *[p.name for p in args.manifest.parent.glob("*_metadata.csv")],
    ):
        shutil.copy2(args.manifest.parent / name, output / name)
    files = sorted(p for p in output.rglob("*") if p.is_file())
    (output / "CHECKSUMS.sha256").write_text(
        "".join(
            f"{sha256_file(p)}  {p.relative_to(output).as_posix()}\n" for p in files
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
