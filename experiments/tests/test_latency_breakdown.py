import json
from pathlib import Path

import pytest

from experiments.latency_breakdown import evaluate, main, read_table


def _write(path: Path, rows: list[tuple[str, str, float]]) -> None:
    lines = ["trial,stage,t_s"]
    lines.extend(f"{trial},{stage},{t_s}" for trial, stage, t_s in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_quantiles_of_two_trials(tmp_path: Path):
    path = tmp_path / "events.csv"
    stages = ("capture", "detect", "confirm", "localize", "aim", "spray")
    rows = []
    for trial, shift in (("a", 0.0), ("b", 1.0)):
        for index, stage in enumerate(stages):
            rows.append((trial, stage, shift + index))
    _write(path, rows)
    payload = evaluate(read_table(path))
    segment = payload["segments_s"]["aim_to_spray"]
    assert segment["n"] == 2
    assert segment["p50_s"] == pytest.approx(1)
    assert segment["max_s"] == pytest.approx(1)


def test_backwards_time_exits(tmp_path: Path):
    path = tmp_path / "events.csv"
    _write(path, [("a", "capture", 2), ("a", "detect", 1), ("a", "confirm", 3),
                  ("a", "localize", 4), ("a", "aim", 5), ("a", "spray", 6)])
    with pytest.raises(SystemExit, match="倒退"):
        evaluate(read_table(path))


def test_script_stacks_the_sample(tmp_path: Path):
    path = tmp_path / "events.csv"
    stages = ("capture", "detect", "confirm", "localize", "aim", "spray")
    _write(path, [("full", stage, float(index)) for index, stage in enumerate(stages)])
    out = tmp_path / "out"
    main(["--events", str(path), "--out", str(out)])
    payload = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert payload["data"] == "测量输入"
    assert (out / "latency-stack.png").is_file()
    assert (out / "latency-stack.svg").is_file()
