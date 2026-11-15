import json
from pathlib import Path

import pytest

from experiments.gimbal_ballistics import main, score_landings


def test_landing_table_requires_three_methods():
    with pytest.raises(SystemExit, match="缺少方式"):
        score_landings(
            [
                {
                    "method": "manual",
                    "x_m": 1,
                    "y_m": 0,
                    "z_m": 0,
                    "landing_x_m": 1.2,
                    "landing_y_m": 0,
                    "landing_z_m": 0,
                }
            ]
        )


def test_synthetic_ballistic_beats_manual_pose(tmp_path: Path):
    out = tmp_path / "out"
    main(["--synthetic", "--seed", "7", "--out", str(out)])
    payload = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert payload["data"] == "合成数据"
    hits = payload["hit_error_m"]
    assert hits["ballistic"] < hits["manual"]
    assert hits["ballistic"] < hits["self_cal"]
    assert payload["convergence"][0]["groups"] == 12
    assert (out / "hit-error.png").is_file()
    assert (out / "convergence.svg").is_file()


def test_missing_field_inputs_exit(tmp_path: Path):
    with pytest.raises(SystemExit, match="实测需要"):
        main(["--out", str(tmp_path / "out")])
