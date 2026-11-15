import json
from pathlib import Path

import pytest

from experiments.gimbal_ballistics import SyntheticConfig, main, score_landings, synthetic_case


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


def test_synthetic_reports_spread_across_seeds(tmp_path: Path):
    out = tmp_path / "out"
    main(["--synthetic", "--seeds", "2", "--seed", "7", "--out", str(out)])
    payload = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert payload["data"] == "合成数据"
    assert payload["config"]["truth_drag"] != payload["config"]["nominal_drag"]
    for name in ("manual", "self_cal", "fitted"):
        stats = payload["hit_error_m"][name]
        assert stats["n"] == 2
        assert stats["max_m"] >= stats["p90_m"] >= stats["mean_m"]
        assert stats["mean_m"] > 0.005
    assert payload["convergence"][0]["groups"] == 12
    assert "std_m" in payload["convergence"][0]
    assert (out / "hit-error.png").is_file()
    assert (out / "convergence.svg").is_file()


def test_noiseless_matched_model_is_rejected():
    cfg = SyntheticConfig(
        seeds=2,
        truth_drag=0.05,
        nominal_drag=0.05,
        breakup_sigma_m=0.0,
        speed_jitter_std=0.0,
    )
    with pytest.raises(SystemExit, match="无噪声"):
        synthetic_case(cfg)


def test_missing_field_inputs_exit(tmp_path: Path):
    with pytest.raises(SystemExit, match="实测需要"):
        main(["--out", str(tmp_path / "out")])
