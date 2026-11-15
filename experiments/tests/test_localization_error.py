import csv
import json
from pathlib import Path

import pytest

from experiments.localization_error import COLUMNS, evaluate, main, synthetic_rows


def test_synthetic_rows_have_three_camera_counts():
    rows = synthetic_rows(seed=3, points=4)
    assert len(rows) == 12
    result = evaluate(rows)
    assert result["overall"]["n"] == 12
    assert set(result["by_camera_count"]) == {"2", "3", "4"}
    assert result["by_camera_count"]["4"]["mean_m"] < result["by_camera_count"]["2"]["mean_m"]


def test_missing_csv_exits(tmp_path: Path):
    with pytest.raises(SystemExit, match="缺少输入文件"):
        main(["--csv", str(tmp_path / "missing.csv"), "--out", str(tmp_path / "out")])


def test_script_writes_json_and_figures(tmp_path: Path):
    out = tmp_path / "out"
    main(["--synthetic", "--points", "4", "--seed", "5", "--out", str(out)])
    payload = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert payload["data"] == "合成数据"
    assert (out / "error-by-cameras.png").is_file()
    assert (out / "error-by-cameras.svg").is_file()
    with (out / "input.csv").open(encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    assert tuple(header) == COLUMNS
