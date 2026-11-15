import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from scipy.stats import chi2

from fire_monitoring_inference.suppression.aim import solve_aim
from fire_monitoring_inference.suppression.ballistics import (
    fit_drag,
    height_at_range,
    integrate,
    landing_range,
    solve_pitch,
)
from fire_monitoring_inference.suppression.calibrate import LaserSample, fit_gimbal
from fire_monitoring_inference.suppression.cli import main
from fire_monitoring_inference.suppression.coverage import cover_probability, max_std
from fire_monitoring_inference.suppression.feedback import corrected_aim, zigzag
from fire_monitoring_inference.suppression.kinematics import (
    NOMINAL_SCALE,
    GimbalParams,
    point_on_ray,
)
from fire_monitoring_inference.suppression.laser import detect_red_dot
from fire_monitoring_inference.suppression.machine import MachineConfig, RoomMachine, Shot
from fire_monitoring_inference.suppression.place import place_name
from fire_monitoring_inference.suppression.voice import prohibited_voice
from fire_monitoring_inference.analysis.rules import classify


def _gimbal() -> GimbalParams:
    return GimbalParams.nominal([0.0, 0.0, 2.2], tilt_zero=4000)


def _position(xyz=(1.5, 2.5, 0.2), std=0.05):
    return {
        "status": "ESTIMATED",
        "xyz": list(xyz),
        "covariance": [[std**2, 0, 0], [0, std**2, 0], [0, 0, std**2]],
    }


def shot(**overrides) -> Shot:
    base = dict(
        now=0.0,
        room_name="101",
        scene="classroom",
        local_fire=True,
        smoke=False,
        analysis={"status": "SUCCEEDED", "has_visible_fire": True, "has_visible_smoke": False, "evidence": {
            "burning_objects": [{"frame_index": 1, "name": "纸", "evidence": "桌面"}],
            "suspected_cause": "open_flame",
            "energized_equipment": False,
            "liquid": False,
            "oil_pan": False,
            "metal_powder": False,
            "person_count": 0,
            "person_location": "",
            "scene_type": "classroom",
            "smoke_color": "none",
            "smoke_density": "none",
            "uncertainties": [],
        }},
        position=_position(),
        heartbeat_ok=True,
        persons=[],
        flame_present=True,
        flame_area=100.0,
        landing=None,
        web_estop=False,
        firmware_latch="CLEAR",
        admin_unlock=False,
        room_size=(9.0, 12.0),
        gimbal=_gimbal(),
        speed=10.0,
        drag=0.05,
        grade="Ⅲ",
        pump_enabled=True,
        zone_ok=True,
        evidence_age_s=1.0,
        max_evidence_age_s=30.0,
        cancelled=False,
        require_vlm=False,
        cooldown_elapsed=True,
        max_std_m=0.5,
        cover_radius_m=1.0,
        cover_threshold=0.5,
        person_distance_m=1.5,
    )
    base.update(overrides)
    return Shot(**base)


def test_self_calibration_recovers_gimbal_parameters():
    truth = GimbalParams(
        p0=np.array([1.2, 0.4, 2.3]),
        yaw=np.deg2rad(25),
        roll=np.deg2rad(1.5),
        pitch=np.deg2rad(-1.0),
        pan_scale=NOMINAL_SCALE * 1.02,
        pan_zero=0.0,
        tilt_scale=NOMINAL_SCALE * 0.98,
        tilt_zero=80.0,
        nozzle_offset=0.18,
    )
    poses = [(pan, tilt) for pan in (-9000, -5000, -1500, 2000, 7000) for tilt in (400, 1800, 3200, 4800)]
    rng = np.random.default_rng(2)
    samples = []
    for index, (pan, tilt) in enumerate(poses):
        distance = 2.2 + (index % 6) * 0.45
        xyz = point_on_ray(truth, pan, tilt, distance) + rng.normal(0, 0.001, 3)
        samples.append(LaserSample(pan, tilt, xyz))
    initial = GimbalParams.nominal([1.32, 0.5, 2.42], yaw=np.deg2rad(12), tilt_zero=0)
    initial.nozzle_offset = 0.08
    fitted = fit_gimbal(samples, initial).params
    assert np.linalg.norm(fitted.p0 - truth.p0) < 0.01
    assert abs(np.rad2deg(fitted.yaw - truth.yaw)) < 0.2
    assert abs(np.rad2deg(fitted.roll - truth.roll)) < 0.2
    assert abs(np.rad2deg(fitted.pitch - truth.pitch)) < 0.2
    assert fitted.pan_scale == pytest.approx(truth.pan_scale, rel=0.005)
    assert fitted.tilt_scale == pytest.approx(truth.tilt_scale, rel=0.005)
    assert fitted.pan_zero == pytest.approx(0, abs=1)
    assert fitted.tilt_zero == pytest.approx(truth.tilt_zero, abs=10)
    assert fitted.nozzle_offset == pytest.approx(truth.nozzle_offset, abs=0.01)


def test_ballistic_inverse_is_within_one_centimetre_and_out_of_range_is_empty():
    speed, drag = 11.0, 0.05
    pitch = np.deg2rad(18)
    height = height_at_range(integrate(pitch, speed, drag, dt=0.001), 3.0)
    solved = solve_pitch(3.0, height, speed, drag, low=np.deg2rad(0), high=np.deg2rad(60))
    assert solved is not None
    again = height_at_range(integrate(solved, speed, drag, dt=0.001), 3.0)
    assert abs(again - height) < 0.01
    assert abs(np.rad2deg(solved - pitch)) < 0.05
    assert solve_pitch(80.0, 0.0, speed, drag, low=0.0, high=np.deg2rad(60)) is None
    assert solve_aim(_gimbal(), np.array([40.0, 0.0, 2.2]), speed, drag) is None


def test_drag_fit_matches_three_landing_ranges():
    truth_speed, truth_drag = 12.0, 0.06
    shots = [
        (np.deg2rad(deg), landing_range(np.deg2rad(deg), truth_speed, truth_drag))
        for deg in (12, 22, 32, 42)
    ]
    fitted = fit_drag(shots, speed0=9.0, drag0=0.02)
    assert fitted.speed == pytest.approx(truth_speed, abs=0.05)
    assert fitted.drag == pytest.approx(truth_drag, abs=0.005)


def test_cover_probability_matches_the_isotropic_chi_square():
    sigma, radius = 0.2, 0.3
    exact = chi2.cdf((radius / sigma) ** 2, df=3)
    estimated = cover_probability(np.eye(3) * sigma**2, radius, samples=40000, seed=1)
    assert estimated == pytest.approx(exact, abs=0.02)
    assert max_std(np.diag([0.01, 0.04, 0.09])) == pytest.approx(0.3)


def test_red_dot_uses_saturation_and_frame_difference():
    previous = np.zeros((40, 40, 3), dtype=np.uint8)
    previous[14:18, 20:24] = (0, 0, 255)
    frame = previous.copy()
    frame[30:34, 8:12] = (0, 0, 255)
    frame[2:6, 2:6] = (200, 200, 200)
    u, v = detect_red_dot(frame, previous)
    assert u == pytest.approx(9.5, abs=1)
    assert v == pytest.approx(31.5, abs=1)
    with pytest.raises(RuntimeError, match="red dot"):
        detect_red_dot(previous, previous)


def test_place_name_uses_room_size():
    assert place_name(8, 10, 9, 12) == "东北角"
    assert place_name(1, 6, 9, 12) == "西侧"
    assert place_name(4.5, 6, 9, 12) == "中部"


def test_electrical_room_prior_prohibits_water_without_qwen():
    resolved = classify(None, "electrical_room")
    assert resolved["water_prohibited"] is True
    assert prohibited_voice(resolved) == "带电火灾，禁止用水，请使用二氧化碳灭火器并切断电源"


def _phases(machine: RoomMachine, item: Shot) -> list[str]:
    return [effect.phase for effect in machine.step(item)]


def test_happy_path_reaches_extinguished_in_order():
    machine = RoomMachine(MachineConfig(pending_s=3, spray_s=5, review_s=5, clear_s=3))
    seen = _phases(machine, shot(smoke=True, local_fire=False))
    assert seen == ["疑似"]
    seen += _phases(machine, shot(now=1))
    assert machine.phase == "待喷"
    seen += _phases(machine, shot(now=4))
    assert machine.phase == "喷射"
    seen += _phases(machine, shot(now=9, flame_present=False))
    assert machine.phase == "复核"
    seen += _phases(machine, shot(now=12, flame_present=False, flame_area=0))
    assert machine.phase == "已扑灭"
    assert seen == ["疑似", "已确认", "瞄准", "待喷", "喷射", "复核", "已扑灭"]
    spray = [effect for effect in machine.step(shot(now=12, flame_present=False))]
    assert spray == []


def test_two_corrections_then_manual_stop():
    machine = RoomMachine(MachineConfig(pending_s=0, spray_s=1, review_s=2, clear_s=3, max_corrections=2))
    machine.step(shot(now=0))
    assert machine.phase == "喷射"
    machine.step(shot(now=1, flame_area=100))
    assert machine.phase == "复核"
    machine.step(shot(now=3, flame_area=100))
    assert machine.corrections == 1
    assert machine.phase == "喷射"
    machine.step(shot(now=4, flame_area=100))
    assert machine.phase == "复核"
    machine.step(shot(now=6, flame_area=100))
    assert machine.corrections == 2
    machine.step(shot(now=7, flame_area=100))
    effects = machine.step(shot(now=9, flame_area=100))
    assert machine.phase == "需人工处置"
    assert effects[-1].stop is True


def test_landing_correction_shifts_the_next_aim_point():
    machine = RoomMachine(MachineConfig(pending_s=0, spray_s=1, review_s=1, clear_s=5))
    machine.step(shot(now=0))
    target = machine.aim_point.copy()
    landing = target + np.array([0.2, -0.1, 0.0])
    machine.step(shot(now=1))
    machine.step(shot(now=2, landing=landing, flame_area=100))
    assert machine.aim_point == pytest.approx(corrected_aim(target, landing))


@pytest.mark.parametrize(
    "phase",
    ["监视", "疑似", "已确认", "瞄准", "待喷", "喷射", "复核", "已扑灭", "需人工处置"],
)
def test_estop_from_every_phase_locks_until_reset_and_admin_unlock(phase):
    machine = RoomMachine()
    machine.phase = phase
    effects = machine.step(shot(web_estop=True))
    assert machine.phase == "锁定"
    assert effects[-1].latch is True
    assert effects[-1].voice == "系统已急停"
    refused = machine.step(shot(web_estop=False, firmware_latch="LATCHED", admin_unlock=True))
    assert machine.phase == "锁定"
    assert refused[-1].detail["reason"] == "ERR_RESET"
    opened = machine.step(shot(web_estop=False, firmware_latch="ARMED", admin_unlock=True))
    assert machine.phase == "监视"
    assert opened[-1].detail["unlock"] is True


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"scene": "electrical_room", "analysis": None, "require_vlm": False}, "WATER_PROHIBITED"),
        ({"scene": "classroom", "analysis": {"status": "SUCCEEDED", "has_visible_fire": True, "evidence": {
            "burning_objects": [],
            "suspected_cause": "electrical_short",
            "energized_equipment": True,
            "liquid": False,
            "oil_pan": False,
            "metal_powder": False,
            "person_count": 0,
            "person_location": "",
            "scene_type": "classroom",
            "smoke_color": "none",
            "smoke_density": "none",
            "uncertainties": [],
        }}}, "WATER_PROHIBITED"),
        ({"persons": [np.array([1.5, 2.5, 0.2])]}, "PERSON"),
        ({"web_estop": False, "heartbeat_ok": False}, "HEARTBEAT"),
        ({"position": {"status": "ESTIMATED", "xyz": [1.5, 2.5, 0.2], "covariance": np.eye(3).tolist()}}, "COVARIANCE"),
        ({"position": {"status": "ESTIMATED", "xyz": [40.0, 0.0, 2.2], "covariance": _position()["covariance"]}}, "OUT_OF_RANGE"),
        ({"local_fire": False, "smoke": True, "manual_spray": True}, "LOCAL_FIRE_NOT_CONFIRMED"),
        ({"require_vlm": True, "analysis": {"status": "FAILED", "has_visible_fire": False, "has_visible_smoke": False}}, "VLM_NOT_CONFIRMED"),
        ({"heartbeat_ok": True, "firmware_latch": "CLEAR", "cooldown_elapsed": False}, "COOLDOWN"),
        ({"zone_ok": False}, "ZONE_NOT_COVERED"),
        ({"pump_enabled": False}, "PUMP_DISABLED"),
        ({"cancelled": True}, "CAMERA_STOPPED"),
        ({"evidence_age_s": 120}, "STALE_EVIDENCE"),
    ],
)
def test_each_interlock_refuses_to_spray(overrides, reason):
    machine = RoomMachine(MachineConfig(pending_s=0, spray_s=5))
    if reason == "LOCAL_FIRE_NOT_CONFIRMED":
        machine.step(shot(local_fire=False, smoke=True))
        effects = machine.step(shot(**overrides))
    else:
        effects = machine.step(shot(**overrides))
    assert machine.phase != "喷射"
    assert any(effect.detail.get("reason") == reason for effect in effects)
    assert not any(effect.run for effect in effects)
    if reason == "OUT_OF_RANGE":
        assert any(effect.detail.get("message") == "超出喷射范围" for effect in effects)
    if reason == "PERSON":
        assert any(effect.voice == "附近有人，请立即撤离" for effect in effects)


def test_low_coverage_designs_a_sweep_instead_of_a_direct_shot():
    wide = {"status": "ESTIMATED", "xyz": [1.5, 2.5, 0.2], "covariance": (np.eye(3) * 0.04).tolist()}
    machine = RoomMachine(MachineConfig(pending_s=0, spray_s=5))
    machine.step(shot(position=wide, cover_radius_m=0.05, cover_threshold=0.99, max_std_m=1.0))
    assert machine.sweep is not None
    assert len(machine.sweep) == len(zigzag(wide["xyz"], wide["covariance"], 0.05))
    assert machine.phase == "喷射"


def test_cli_calibrate_and_fit_drag(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    truth = _gimbal()
    samples = []
    for index, (pan, tilt) in enumerate((p, t) for p in (-2000, 0, 2000, 5000) for t in (1000, 2500, 4000)):
        samples.append(
            {
                "pan_cdeg": pan,
                "tilt_cdeg": tilt,
                "xyz": point_on_ray(truth, pan, tilt, 3.0).tolist(),
            }
        )
    path = tmp_path / "laser.json"
    path.write_text(json.dumps(samples), encoding="utf-8")
    main(["calibrate", "--p0", "0.05,0.05,2.3", "--tilt-zero", "4000", "--samples", str(path)])
    payload = json.loads(capsys.readouterr().out)
    assert payload["residuals_m"][0] < 0.05
    landings = [
        {"pitch_deg": deg, "range_m": landing_range(np.deg2rad(deg), 12.0, 0.06)}
        for deg in (15, 25, 35)
    ]
    drag_path = tmp_path / "drag.json"
    drag_path.write_text(json.dumps(landings), encoding="utf-8")
    main(["fit-drag", "--samples", str(drag_path)])
    fitted = json.loads(capsys.readouterr().out)
    assert fitted["speed"] == pytest.approx(12.0, abs=0.05)
