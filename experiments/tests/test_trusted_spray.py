import json
from pathlib import Path

from experiments.trusted_spray import main, sweep


def test_hit_rate_falls_as_covariance_grows():
    payload = sweep(40, 11)
    assert payload["data"] == "合成数据"
    rows = payload["sweep"]

    def at(sigma: float) -> dict:
        return min(rows, key=lambda row: abs(row["sigma_m"] - sigma))

    assert at(0.05)["fixed_point"]["hit_rate"] > at(0.8)["fixed_point"]["hit_rate"]
    assert at(0.35)["adaptive_sweep"]["hit_rate"] > at(0.35)["fixed_point"]["hit_rate"]
    assert at(0.8)["adaptive_sweep"]["water_s"] > at(0.05)["adaptive_sweep"]["water_s"]


def test_script_writes_the_sweep(tmp_path: Path):
    out = tmp_path / "out"
    main(["--draws", "20", "--seed", "11", "--out", str(out)])
    payload = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert payload["draws"] == 20
    assert (out / "sigma-sweep.png").is_file()
    assert (out / "sigma-sweep.svg").is_file()
