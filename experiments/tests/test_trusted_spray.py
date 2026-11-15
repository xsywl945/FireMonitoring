import json
from pathlib import Path

from experiments.trusted_spray import main, sweep


def test_large_sigma_refuses_instead_of_spraying():
    payload = sweep(40, 11)
    assert payload["data"] == "合成数据"
    rows = payload["sweep"]

    def at(sigma: float) -> dict:
        return min(rows, key=lambda row: abs(row["sigma_m"] - sigma))

    small = at(0.05)
    large = at(0.8)
    assert small["fixed_point"]["hit_rate"] > large["fixed_point"]["hit_rate"]
    assert large["ellipse_gated"]["refusal_rate"] > small["ellipse_gated"]["refusal_rate"]
    assert large["ellipse_gated"]["water_s"] < large["ellipse"]["water_s"]
    assert large["fixed_point"]["refusal_rate"] == 0
    assert payload["cover_threshold"] == 0.5


def test_script_writes_the_sweep(tmp_path: Path):
    out = tmp_path / "out"
    main(["--draws", "20", "--seed", "11", "--out", str(out)])
    payload = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert payload["draws"] == 20
    assert (out / "sigma-sweep.png").is_file()
    assert (out / "calibration.svg").is_file()
