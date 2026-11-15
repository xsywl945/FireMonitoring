from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import numpy as np

from experiments.plotting import configure_font, require_file, save_figure, write_json

STAGES = ("capture", "detect", "confirm", "localize", "aim", "spray")
STAGE_LABEL = {
    "capture": "采集",
    "detect": "检测",
    "confirm": "确认",
    "localize": "定位",
    "aim": "瞄准",
    "spray": "出水",
}
SEGMENT_PAIRS = tuple(zip(STAGES, STAGES[1:]))
SEGMENTS = tuple(f"{left}_to_{right}" for left, right in SEGMENT_PAIRS)
SEGMENT_LABEL = {
    f"{left}_to_{right}": f"{STAGE_LABEL[left]}→{STAGE_LABEL[right]}" for left, right in SEGMENT_PAIRS
}


def _quantile(values: list[float]) -> dict:
    if not values:
        raise SystemExit("没有延迟样本")
    array = np.asarray(values, dtype=float)
    return {
        "n": int(array.size),
        "p50_s": float(np.quantile(array, 0.5)),
        "p90_s": float(np.quantile(array, 0.9)),
        "max_s": float(np.max(array)),
    }


def durations(trials: dict[str, dict[str, float]]) -> dict[str, list[float]]:
    if not trials:
        raise SystemExit("事件表是空的")
    segments = {name: [] for name in SEGMENTS}
    for trial, stamps in trials.items():
        missing = [stage for stage in STAGES if stage not in stamps]
        if missing:
            raise SystemExit(f"{trial} 缺少阶段：" + "、".join(missing))
        times = [float(stamps[stage]) for stage in STAGES]
        if any(right < left for left, right in zip(times, times[1:])):
            raise SystemExit(f"{trial} 的阶段时间倒退")
        for name, left, right in zip(SEGMENTS, times[:-1], times[1:], strict=True):
            segments[name].append(right - left)
    return segments


def evaluate(trials: dict[str, dict[str, float]]) -> dict:
    segments = durations(trials)
    return {
        "trials": trials,
        "segments_s": {name: _quantile(values) for name, values in segments.items()},
    }


def read_table(path: Path) -> dict[str, dict[str, float]]:
    require_file(path)
    if path.suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise SystemExit("延迟 JSON 必须是数组")
        rows = payload
    else:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or tuple(reader.fieldnames) != ("trial", "stage", "t_s"):
                raise SystemExit("延迟 CSV 表头必须是：trial,stage,t_s")
            rows = list(reader)
    trials: dict[str, dict[str, float]] = {}
    for row in rows:
        stage = row["stage"]
        if stage not in STAGES:
            raise SystemExit(f"未知阶段 {stage}")
        trials.setdefault(str(row["trial"]), {})[stage] = float(row["t_s"])
    return trials


def _first_detection(pack_root: Path, relative: str) -> float:
    payload = json.loads((pack_root / relative).read_text(encoding="utf-8"))
    for frame in payload["frames"]:
        for boxes in frame["cameras"].values():
            if any(item["class_name"] in {"fire", "smoke"} for item in boxes):
                return float(frame["t"])
    raise SystemExit("检测文件里没有火或烟")


def run_demo(script: str, work: Path) -> tuple[dict[str, dict[str, float]], str, dict[str, float]]:
    from fire_monitoring.config import load_config
    from fire_monitoring.db import make_engine
    from fire_monitoring.evidence.store import MemoryStore
    from fire_monitoring.main import create_app

    work.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "config.example.json")
    config.demo.enabled = True
    config.demo.pack = str(root / "data" / "demo" / "synthetic-classroom")
    config.demo.hardware = "sim"
    config.demo.detector = "replay"
    config.demo.pump_run = True
    config.pump.journal_path = str(work / "pump.sqlite3")
    config.suppression.gimbal_path = str(work / "gimbal.json")
    config.llm.enabled = False
    config.sms.enabled = False
    app = create_app(
        config,
        engine=make_engine(f"sqlite:///{work / 'demo.db'}"),
        evidence=MemoryStore(),
        start_worker=False,
    )
    demo = app.state.demo
    player = demo.player
    marks: dict[str, float] = {}
    started = time.perf_counter()
    wall: dict[str, float] = {}
    fire_alert: list[int | None] = [None]

    def consume(camera, jpeg, boxes):
        if "capture" not in wall:
            wall["capture"] = time.perf_counter() - started
        if "detect" not in wall and any(item["class_name"] in {"fire", "smoke"} for item in boxes):
            wall["detect"] = time.perf_counter() - started
        return original_consume(camera, jpeg, boxes)

    def publish(payload: dict) -> None:
        kind = payload.get("kind")
        alert_id = payload.get("alert_id")
        if kind == "CONFIRMED" and payload.get("alert_type") == "FIRE" and fire_alert[0] is None:
            fire_alert[0] = alert_id
            marks["confirm"] = float(player.clock.seconds)
            wall["confirm"] = time.perf_counter() - started
        stage = {"LOCALIZED": "localize", "SUP_AIM": "aim", "SUP_SPRAY": "spray"}.get(kind)
        if stage and alert_id == fire_alert[0] and stage not in marks:
            marks[stage] = float(player.clock.seconds)
            wall[stage] = time.perf_counter() - started
        original_publish(payload)

    original_consume = player._consume
    original_publish = demo.events.publish
    player._consume = consume
    demo.events.publish = publish
    pack = demo.pack
    try:
        player.start(script, 0)
        player.join(120)
    finally:
        demo.close()
    missing = [stage for stage in ("confirm", "localize", "aim", "spray") if stage not in marks]
    if missing:
        raise SystemExit("演示没有走到：" + "、".join(missing))
    detection = pack["scripts"][script]["detections"]
    stamps = {
        "capture": 0.0,
        "detect": _first_detection(pack["root"], detection),
        "confirm": marks["confirm"],
        "localize": marks["localize"],
        "aim": marks["aim"],
        "spray": marks["spray"],
    }
    data = "合成数据" if pack.get("synthetic") else "演示录像"
    return {script: stamps}, data, wall


def _plot(trials: dict[str, dict[str, float]], directory: Path, title: str) -> None:
    configure_font()
    import matplotlib.pyplot as plt

    colors = ["#0072B2", "#56B4E9", "#009E73", "#E69F00", "#D55E00"]
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    names = list(trials)
    left = np.zeros(len(names))
    for segment, color in zip(SEGMENTS, colors, strict=True):
        width = []
        for name in names:
            stamps = trials[name]
            start = STAGES[SEGMENTS.index(segment)]
            end = STAGES[SEGMENTS.index(segment) + 1]
            width.append(stamps[end] - stamps[start])
        ax.barh(names, width, left=left, color=color, label=SEGMENT_LABEL[segment])
        left = left + np.asarray(width)
    ax.set_xlabel("剧本时间 (s)")
    ax.set_title(title)
    ax.legend(frameon=False, ncol=3, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.22))
    fig.tight_layout()
    save_figure(fig, directory, "latency-stack")


def _write_csv(path: Path, trials: dict[str, dict[str, float]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("trial", "stage", "t_s"))
        writer.writeheader()
        for trial, stamps in trials.items():
            for stage in STAGES:
                writer.writerow({"trial": trial, "stage": stage, "t_s": stamps[stage]})


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="从事件表分解各段延迟")
    parser.add_argument("--events", type=Path)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--script", default="full")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.demo == bool(args.events):
        raise SystemExit("指定 --events 或 --demo 其中之一")
    wall = None
    if args.demo:
        trials, data, wall = run_demo(args.script, args.out)
        args.out.mkdir(parents=True, exist_ok=True)
        _write_csv(args.out / "events.csv", trials)
    else:
        trials = read_table(args.events)
        data = "测量输入"
    payload = {"data": data, "clock": "剧本时间", **evaluate(trials)}
    if wall is not None:
        payload["wall_clock_s"] = wall
    if data == "合成数据":
        payload["note"] = "堆叠图用剧本时钟。wall_clock_s 是同一次播放的墙钟，确认到定位的耗时看这里。"
    args.out.mkdir(parents=True, exist_ok=True)
    write_json(args.out / "result.json", payload)
    title = "延迟分解（合成数据）" if data == "合成数据" else "延迟分解"
    _plot(trials, args.out, title)


if __name__ == "__main__":
    main()
