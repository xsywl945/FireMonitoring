import json
from pathlib import Path

import numpy as np
import pytest

from experiments.nist_hrr import evaluate, main, measure_frame, synthetic_inputs


def test_synthetic_inversion_keeps_the_growth_bin(tmp_path: Path):
    out = tmp_path / "out"
    main(["--synthetic", "--out", str(out)])
    payload = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert payload["data"] == "合成数据"
    assert payload["relative_error"]["mean"] < 0.02
    assert payload["growth"]["correct"] is True
    assert payload["growth"]["measured_bin"] == "ultrafast"
    reached = next(item for item in payload["thresholds"] if item["level_kw"] == 100)
    assert reached["reached"] is True
    assert abs(reached["error_s"]) < 1.5
    assert (out / "hrr.png").is_file()
    assert (out / "hrr.svg").is_file()


def test_missing_hrr_exits(tmp_path: Path):
    with pytest.raises(SystemExit, match="需要 --hrr"):
        main(["--out", str(tmp_path / "out")])


def test_measure_frame_uses_the_bright_span():
    frame = np.zeros((40, 20, 3), dtype=np.uint8)
    frame[10:30, 8:12] = (255, 255, 255)
    assert measure_frame(frame, px_per_m=10) == pytest.approx(2.0)


def test_evaluate_rejects_a_flat_curve():
    times, measured, flames = synthetic_inputs()
    measured[:] = 20
    with pytest.raises(ValueError, match="not growing"):
        evaluate(times, measured, flames)
