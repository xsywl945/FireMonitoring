from datetime import UTC, datetime, timedelta

from fire_monitoring_inference.temporal import (
    TemporalConfig,
    TemporalState,
    TemporalStateMachine,
)


def test_n_of_m_state_machine_and_cooldown() -> None:
    config = TemporalConfig(
        n=3,
        m=5,
        candidate_n=2,
        min_confidence=0.5,
        clear_frames=2,
        cooldown_ms=1000,
    )
    machine = TemporalStateMachine(
        camera_id=1,
        view_role="VIEW_A",
        class_name="fire",
        config=config,
    )
    start = datetime(2026, 7, 16, tzinfo=UTC)

    assert machine.update(timestamp=start, confidence=0.8, bbox_area=0.1) is None
    suspect = machine.update(
        timestamp=start + timedelta(milliseconds=200), confidence=0.7, bbox_area=0.11
    )
    assert suspect is not None
    assert suspect.state == TemporalState.SUSPECT
    assert suspect.transitioned_from == TemporalState.NORMAL

    still_suspect = machine.update(timestamp=start + timedelta(milliseconds=400), confidence=None)
    assert still_suspect is not None
    confirmed = machine.update(
        timestamp=start + timedelta(milliseconds=600), confidence=0.9, bbox_area=0.13
    )
    assert confirmed is not None
    assert confirmed.state == TemporalState.CONFIRMED
    assert confirmed.effective_frames == 3
    assert confirmed.duration_ms == 600
    assert confirmed.area_growth > 0

    assert machine.update(timestamp=start + timedelta(milliseconds=800), confidence=None)
    assert machine.update(timestamp=start + timedelta(milliseconds=1000), confidence=None) is None
    assert machine.state == TemporalState.COOLDOWN
    assert machine.update(timestamp=start + timedelta(milliseconds=1500), confidence=0.99) is None

    # After cooldown, the old event cannot contribute frames to a new event.
    assert machine.update(timestamp=start + timedelta(milliseconds=2100), confidence=0.99) is None
    assert machine.state == TemporalState.NORMAL


def test_temporal_config_rejects_invalid_threshold_order() -> None:
    try:
        TemporalConfig(n=4, m=3)
    except ValueError as exc:
        assert "candidate_n <= n <= m" in str(exc)
    else:
        raise AssertionError("invalid N/M configuration was accepted")
