from datetime import UTC, datetime, timedelta

import pytest

from fire_monitoring_inference.fusion import DualCameraFusion, FusionConfig, FusionStatus
from fire_monitoring_inference.temporal import TemporalEvidence, TemporalState


def evidence(
    camera_id: int,
    role: str,
    state: TemporalState,
    timestamp: datetime,
    *,
    class_name: str = "fire",
    score: float = 0.8,
) -> TemporalEvidence:
    return TemporalEvidence(
        camera_id=camera_id,
        view_role=role,
        class_name=class_name,
        state=state,
        score=score,
        max_confidence=score,
        average_confidence=score,
        effective_frames=3 if state == TemporalState.CONFIRMED else 1,
        duration_ms=400,
        area_growth=0.1,
        first_seen_at=timestamp - timedelta(milliseconds=400),
        last_seen_at=timestamp,
    )


def test_two_synchronized_confirmations_raise_score_and_severity() -> None:
    now = datetime(2026, 7, 16, tzinfo=UTC)
    fusion = DualCameraFusion(FusionConfig(sync_window_ms=500))
    decision = fusion.decide(
        [
            evidence(1, "VIEW_A", TemporalState.CONFIRMED, now, score=0.8),
            evidence(
                2,
                "VIEW_B",
                TemporalState.CONFIRMED,
                now + timedelta(milliseconds=100),
                score=0.9,
            ),
        ],
        now=now + timedelta(milliseconds=100),
    )

    assert decision.status == FusionStatus.CONFIRMED
    assert decision.fusion_mode == "DUAL_CAMERA"
    assert decision.score == pytest.approx(0.95)
    assert decision.severity == "CRITICAL"
    assert len(decision.observations) == 2


def test_stale_peer_is_not_fused_and_offline_peer_marks_degraded() -> None:
    now = datetime(2026, 7, 16, tzinfo=UTC)
    fusion = DualCameraFusion(FusionConfig(sync_window_ms=500))
    decision = fusion.decide(
        [
            evidence(
                1,
                "VIEW_A",
                TemporalState.CONFIRMED,
                now - timedelta(seconds=1),
            ),
            evidence(2, "VIEW_B", TemporalState.CONFIRMED, now),
        ],
        camera_health={1: False, 2: True},
        now=now,
    )

    assert decision.status == FusionStatus.CONFIRMED
    assert decision.fusion_mode == "SINGLE_CAMERA"
    assert decision.degraded is True
    assert decision.observations[0].camera_id == 2


def test_confirmed_plus_suspect_preserves_confirmation() -> None:
    now = datetime(2026, 7, 16, tzinfo=UTC)
    decision = DualCameraFusion().decide(
        [
            evidence(1, "VIEW_A", TemporalState.CONFIRMED, now),
            evidence(2, "VIEW_B", TemporalState.SUSPECT, now, score=0.55),
        ],
        now=now,
    )
    assert decision.status == FusionStatus.CONFIRMED
    assert decision.fusion_mode == "DUAL_CAMERA"
