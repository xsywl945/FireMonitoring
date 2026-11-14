from fire_monitoring_inference.analysis.severity import grade_incident
from fire_monitoring_inference.analysis.spread import analyze_spread


def _track():
    return [
        {"t": 0.0, "left": [0.0, 0.0], "right": [1.0, 0.0]},
        {"t": 10.0, "left": [0.0, 1.0], "right": [1.0, 1.0]},
    ]


def test_spread_velocity_and_extrapolation_hit_a_combustible_region():
    regions = [{"name": "试剂柜", "polygon": [[-1, 3.5], [2, 3.5], [2, 5], [-1, 5]]}]
    spread = analyze_spread(_track(), regions)
    assert spread["speed_m_s"] == pytest_approx(0.1)
    assert spread["direction_deg"] == pytest_approx(90)
    assert spread["horizon_30s"][3][1] == pytest_approx(4)
    assert {item["horizon_s"] for item in spread["hits"]} >= {30, 60}
    level = grade_incident(
        q_kw=1,
        growth_bin=None,
        dense_smoke=False,
        people=False,
        scene_risk=0,
        scene_label="教室",
        spread_hits=spread["hits"],
    )
    untouched = grade_incident(
        q_kw=1,
        growth_bin=None,
        dense_smoke=False,
        people=False,
        scene_risk=0,
        scene_label="教室",
        spread_hits=[],
    )
    assert untouched["grade"] == "Ⅰ"
    assert level["grade"] == "Ⅱ"
    assert any("试剂柜" in reason for reason in level["reasons"])


def pytest_approx(value):
    import pytest

    return pytest.approx(value)
