from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parents[1]
FONT_CANDIDATES = (
    Path("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"),
    ROOT / "apps/server/src/fire_monitoring/assets/wqy-microhei.ttc",
)

_FONT_NAME: str | None = None


def configure_font() -> str:
    global _FONT_NAME
    if _FONT_NAME is not None:
        return _FONT_NAME
    chosen = next((path for path in FONT_CANDIDATES if path.is_file()), None)
    if chosen is None:
        raise RuntimeError("没有可用的中文字体")
    font_manager.fontManager.addfont(str(chosen))
    name = font_manager.FontProperties(fname=str(chosen)).get_name()
    plt.rcParams["font.family"] = [name, "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    _FONT_NAME = name
    return name


def save_figure(fig, directory: Path, stem: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    fig.savefig(directory / f"{stem}.png", dpi=160, bbox_inches="tight")
    fig.savefig(directory / f"{stem}.svg", bbox_inches="tight")
    plt.close(fig)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def require_file(path: Path) -> Path:
    if not path.is_file():
        raise SystemExit(f"缺少输入文件：{path}")
    return path
