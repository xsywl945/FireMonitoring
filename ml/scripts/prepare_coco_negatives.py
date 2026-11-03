from __future__ import annotations

import argparse
import csv
import json
import random
import re
import urllib.request
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

PATTERNS = {
    "lights": r"\b(?:traffic lights?|lamps?|neon|headlights?)\b",
    "sunset": r"\b(?:sunset|sunrise)\b",
    "red_objects": r"\bred\b",
    "screens": r"\b(?:television|monitor|screen)\b",
    "steam_fog": r"\b(?:steam|fog|mist|foggy)\b",
}
EXCLUDE = r"\b(?:fires?|flames?|smoke|smoking|burning|candles?|fireplace|bonfire|fireworks|locomotives?|trains?|chimney|engines?|stoves?|ovens?|grill|cooking)\b"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--per-category", type=int, default=600)
    parser.add_argument("--images-zip", type=Path)
    parser.add_argument("--exclusions", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.annotations.read_text(encoding="utf-8"))
    with args.exclusions.open(encoding="utf-8", newline="") as handle:
        excluded = {r["filename"] for r in csv.DictReader(handle)}
    captions = defaultdict(list)
    for item in data["annotations"]:
        captions[item["image_id"]].append(item["caption"])
    licenses = {item["id"]: item["url"] for item in data["licenses"]}
    images = data["images"].copy()
    random.Random(42).shuffle(images)
    counts = Counter()
    selected = []
    for item in images:
        text = " ".join(captions[item["id"]]).lower()
        if re.search(EXCLUDE, text):
            continue
        categories = [
            key
            for key, pattern in PATTERNS.items()
            if re.search(pattern, text) and counts[key] < args.per_category
        ]
        if not categories:
            continue
        category = min(categories, key=lambda key: counts[key])
        counts[category] += 1
        selected.append(
            dict(
                filename=item["file_name"],
                category=category,
                group=f"coco:{item['id']}",
                group_method="coco_image_id",
                source_url=item["coco_url"],
                original_url=item["flickr_url"],
                license=licenses[item["license"]],
                selection=f"COCO 2017 train captions: {category}; exclude {EXCLUDE}",
                captions=text,
            )
        )
    selected = [r for r in selected if r["filename"] not in excluded]
    counts = Counter(r["category"] for r in selected)
    directory = args.output / "train" / "images"
    directory.mkdir(parents=True, exist_ok=True)

    def download(row):
        path = directory / row["filename"]
        if not path.exists():
            temporary = path.with_suffix(".part")
            with urllib.request.urlopen(row["source_url"], timeout=60) as response:
                temporary.write_bytes(response.read())
            temporary.replace(path)
        with Image.open(path) as image:
            image.verify()

    if args.images_zip:
        with zipfile.ZipFile(args.images_zip) as archive:
            for row in selected:
                name = row["source_url"].split("/")[-2] + "/" + row["filename"]
                (directory / row["filename"]).write_bytes(archive.read(name))
                with Image.open(directory / row["filename"]) as image:
                    image.verify()
    else:
        with ThreadPoolExecutor(max_workers=4) as pool:
            for _ in pool.map(download, selected):
                pass
    with (args.output / "metadata.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(selected[0]))
        writer.writeheader()
        writer.writerows(selected)
    print(json.dumps(dict(images=len(selected), categories=dict(counts))))


if __name__ == "__main__":
    main()
