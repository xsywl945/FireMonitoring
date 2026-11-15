from __future__ import annotations


def spoken_room(name: str) -> str:
    if any(token in name for token in ("室", "间", "廊", "厨", "舍")):
        return name
    return f"{name}教室"


def place_name(x: float, y: float, width: float, depth: float) -> str:
    if width <= 0 or depth <= 0:
        raise ValueError("room size must be positive")
    east = "东" if x >= width * 2 / 3 else "西" if x <= width / 3 else ""
    north = "北" if y >= depth * 2 / 3 else "南" if y <= depth / 3 else ""
    if east and north:
        return f"{east}{north}角"
    if east or north:
        return f"{east}{north}侧"
    return "中部"
