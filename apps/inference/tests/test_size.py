import pytest

from fire_monitoring_inference.analysis.size import (
    camera_depth,
    flame_length_m,
    heat_release_kw,
    summarize_views,
)


def test_heskestad_inversion_round_trips():
    diameter = 0.3
    heat = 80.0
    height = flame_length_m(heat, diameter)
    assert heat_release_kw(height, diameter) == pytest.approx(heat, rel=1e-6)


def test_multi_view_height_is_the_median_and_q_follows_heskestad():
    views = [
        {"h_px": 80, "w_px": 40, "z_m": 2.0, "fx": 400, "fy": 200},
        {"h_px": 120, "w_px": 60, "z_m": 3.0, "fx": 600, "fy": 300},
        {"h_px": 200, "w_px": 50, "z_m": 4.0, "fx": 500, "fy": 400},
    ]
    summary = summarize_views(views)
    heights = [0.8, 1.2, 2.0]
    diameters = [0.2, 0.3, 0.4]
    assert summary["height_m"] == pytest.approx(sorted(heights)[1])
    assert summary["diameter_m"] == pytest.approx(sorted(diameters)[1])
    assert summary["q_kw"] == pytest.approx(
        heat_release_kw(summary["height_m"], summary["diameter_m"])
    )
    assert summary["estimated"] is True


def test_camera_depth_of_a_point_in_front_of_the_pinhole():
    calibration = {
        "intrinsics": [[800, 0, 320], [0, 800, 240], [0, 0, 1]],
        "distortion": [0, 0, 0, 0, 0],
        "landmarks": [
            {"world_m": [0, 0, 0], "pixel": [320, 240]},
            {"world_m": [1, 0, 0], "pixel": [480, 240]},
            {"world_m": [0, 1, 0], "pixel": [320, 80]},
            {"world_m": [1, 1, 0], "pixel": [480, 80]},
        ],
    }
    depth = camera_depth([0.5, 0.5, 0], calibration, 2.0)
    assert depth == pytest.approx(5.0, rel=0.05)
