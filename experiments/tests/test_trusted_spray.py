import json
from pathlib import Path

from experiments.trusted_spray import main, run


def test_three_strategies_report_water_and_hits():
    payload = run(2, 11)
    assert payload["data"] == "合成数据"
    names = set(payload["strategies"])
    assert names == {"fixed_point", "fixed_sweep", "adaptive_sweep"}
    fixed = payload["strategies"]["fixed_point"]["water_s_mean"]
    sweep = payload["strategies"]["fixed_sweep"]["water_s_mean"]
    assert sweep > fixed
    assert payload["calibration"]["fixed_point"]


def test_script_writes_figures(tmp_path: Path):
    out = tmp_path / "out"
    main(["--trials", "2", "--seed", "11", "--out", str(out)])
    payload = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert payload["trials"] == 2
    assert (out / "hit-rate.png").is_file()
    assert (out / "calibration.svg").is_file()
