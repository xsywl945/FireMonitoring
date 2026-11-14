import math

import pytest

from fire_monitoring_inference.analysis.growth import fit_area, fit_heat_release, nearest_bin
from fire_monitoring_inference.analysis.rules import load_rules


@pytest.mark.parametrize("name", ["slow", "medium", "fast", "ultrafast"])
def test_synthetic_heat_release_matches_its_growth_bin(name):
    alpha = load_rules()["growth_bins"][name]
    samples = [(float(t), alpha * t * t) for t in range(1, 22)]
    fitted = fit_heat_release(samples)
    assert fitted["bin"] == name
    assert fitted["alpha"] == pytest.approx(alpha, rel=1e-6)
    assert fitted["t0"] == pytest.approx(0, abs=1e-6)
    last = 21
    assert fitted["seconds_to_100kw"] == pytest.approx(math.sqrt(100 / alpha) - last, rel=1e-6)
    assert fitted["seconds_to_500kw"] == pytest.approx(math.sqrt(500 / alpha) - last, rel=1e-6)


@pytest.mark.parametrize(
    "alpha,name",
    [(0.00293, "slow"), (0.02, "medium"), (0.08, "fast"), (0.12, "ultrafast")],
)
def test_nearest_growth_bin_uses_absolute_distance(alpha, name):
    assert nearest_bin(alpha) == name


def test_area_growth_reports_rate_and_doubling_time():
    samples = [(0.0, 100.0), (10.0, 200.0), (20.0, 400.0)]
    fitted = fit_area(samples)
    assert fitted["doubling_time_s"] == pytest.approx(10)
    assert fitted["area_rate_px2_per_s"] > 0
    assert "倍增" in fitted["reason"]


def test_short_heat_release_window_is_rejected():
    alpha = 0.01172
    samples = [(float(t), alpha * t * t) for t in range(1, 6)]
    with pytest.raises(ValueError, match="10 to 30"):
        fit_heat_release(samples)
