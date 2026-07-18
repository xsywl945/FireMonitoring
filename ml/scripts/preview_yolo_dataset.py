#!/usr/bin/env python3
"""Draw a deterministic contact sheet for manual YOLO label verification."""

from __future__ import annotations

import argparse
import math
import random
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont, ImageOps

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
COLORS = {0: "#ff3b30", 1: "#007aff"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--split", choices=("train", "val", "test"), default="train")
    parser.add_argument("--count", type=int, default=24)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--columns", type=int, default=4)
    return parser.parse_args()


def resolve_split(data_file: Path, split: str) -> tuple[Path, dict[int, str]]:
    config = yaml.safe_load(data_file.read_text(encoding="utf-8"))
    root = Path(config.get("path", data_file.parent))
    if not root.is_absolute():
        root = (data_file.parent / root).resolve()
    value = config.get(split)
    if not isinstance(value, str):
        raise ValueError(f"YAML has no string path for split '{split}'")
    image_dir = Path(value)
    if not image_dir.is_absolute():
        image_dir = root / image_dir
    raw_names = config.get("names", {})
    if isinstance(raw_names, list):
        names = {index: str(name) for index, name in enumerate(raw_names)}
    else:
        names = {int(index): str(name) for index, name in raw_names.items()}
    return image_dir.resolve(), names


def label_path(image_path: Path) -> Path:
    parts = list(image_path.parts)
    try:
        index = len(parts) - 1 - parts[::-1].index("images")
    except ValueError as exc:
        raise ValueError(f"Image path does not contain an images directory: {image_path}") from exc
    parts[index] = "labels"
    return Path(*parts).with_suffix(".txt")


def draw_sample(image_path: Path, names: dict[int, str], size: tuple[int, int]) -> Image.Image:
    with Image.open(image_path) as opened:
        original = ImageOps.exif_transpose(opened).convert("RGB")
    width, height = original.size
    draw = ImageDraw.Draw(original)
    font = ImageFont.load_default()
    label_file = label_path(image_path)
    if label_file.exists():
        for line in label_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            class_id_raw, x_raw, y_raw, w_raw, h_raw = line.split()
            class_id = int(class_id_raw)
            x, y, box_w, box_h = map(float, (x_raw, y_raw, w_raw, h_raw))
            x1 = (x - box_w / 2) * width
            y1 = (y - box_h / 2) * height
            x2 = (x + box_w / 2) * width
            y2 = (y + box_h / 2) * height
            color = COLORS.get(class_id, "#ffcc00")
            draw.rectangle((x1, y1, x2, y2), outline=color, width=max(2, width // 300))
            text = f"{class_id}:{names.get(class_id, '?')}"
            text_box = draw.textbbox((x1, y1), text, font=font)
            draw.rectangle(text_box, fill=color)
            draw.text((x1, y1), text, fill="white", font=font)
    contained = ImageOps.contain(original, size)
    tile = Image.new("RGB", size, "#1c1c1e")
    tile.paste(contained, ((size[0] - contained.width) // 2, 0))
    caption = image_path.name[:48]
    ImageDraw.Draw(tile).text((6, size[1] - 16), caption, fill="white", font=font)
    return tile


def main() -> int:
    args = parse_args()
    data_file = args.data.expanduser().resolve()
    image_dir, names = resolve_split(data_file, args.split)
    images = sorted(
        path
        for path in image_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not images:
        raise SystemExit(f"No images found in {image_dir}")
    rng = random.Random(args.seed)
    selected = rng.sample(images, min(args.count, len(images)))
    columns = max(1, args.columns)
    rows = math.ceil(len(selected) / columns)
    tile_size = (360, 270)
    sheet = Image.new("RGB", (columns * tile_size[0], rows * tile_size[1]), "black")
    for index, image_path in enumerate(selected):
        tile = draw_sample(image_path, names, tile_size)
        sheet.paste(tile, ((index % columns) * tile_size[0], (index // columns) * tile_size[1]))
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=92)
    print(f"Wrote {len(selected)} annotated samples to {output}")
    print("Expected colors: red=0:fire, blue=1:smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
