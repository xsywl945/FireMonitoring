from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from fire_monitoring_inference.temporal import TemporalConfig, TemporalState, TemporalStateMachine

from ..config import AppConfig
from ..localization.observe import SourceObservation, latest_in_window, source_from_box


@dataclass(frozen=True)
class DetectionHit:
    class_name: str
    confidence: float
    bbox_xyxy: tuple[float, float, float, float]


@dataclass(frozen=True)
class FrameShot:
    camera_id: int
    jpeg: bytes
    captured_at: datetime
    width: int
    height: int


@dataclass
class AlertDraft:
    room_id: int
    alert_type: str
    started_at: datetime
    sources: list[SourceObservation]
    frames: list[FrameShot]
    pump_observations: list[dict]


@dataclass
class DetectionState:
    trackers: dict[tuple[int, int, str], TemporalStateMachine] = field(default_factory=dict)
    observations: dict[tuple[int, str], list[SourceObservation]] = field(default_factory=dict)
    frames: dict[int, FrameShot] = field(default_factory=dict)
    episode_open: dict[int, bool] = field(default_factory=dict)
    latest: dict[tuple[int, int, str], object] = field(default_factory=dict)


def temporal_config_for(config: AppConfig, class_name: str) -> TemporalConfig:
    thresholds = config.model.thresholds
    minimum = thresholds.fire if class_name == "fire" else thresholds.smoke
    return TemporalConfig(
        n=config.temporal.n,
        m=config.temporal.m,
        candidate_n=config.temporal.candidate_n,
        min_confidence=minimum,
        clear_frames=config.temporal.clear_frames,
        cooldown_ms=config.temporal.cooldown_ms,
    )


def consume_frame(
    *,
    room_id: int,
    camera_id: int,
    bound_camera_ids: list[int],
    detections: list[DetectionHit],
    jpeg: bytes,
    width: int,
    height: int,
    timestamp: datetime,
    state: DetectionState,
    config: AppConfig,
    on_alert,
) -> dict:
    limits = {"fire": config.model.thresholds.fire, "smoke": config.model.thresholds.smoke}
    kept = [item for item in detections if item.confidence >= limits[item.class_name]]
    state.frames[camera_id] = FrameShot(
        camera_id=camera_id,
        jpeg=jpeg,
        captured_at=timestamp,
        width=width,
        height=height,
    )
    just_confirmed = False
    confirmed_evidence = {}
    for class_name in ("fire", "smoke"):
        matches = [item for item in kept if item.class_name == class_name]
        strongest = max(matches, key=lambda item: item.confidence, default=None)
        tracker_key = (room_id, camera_id, class_name)
        tracker = state.trackers.get(tracker_key)
        if tracker is None:
            tracker = TemporalStateMachine(
                camera_id=camera_id,
                view_role="SINGLE",
                class_name=class_name,
                config=temporal_config_for(config, class_name),
            )
            state.trackers[tracker_key] = tracker
        if strongest is None:
            confidence = None
            area = 0.0
        else:
            confidence = strongest.confidence
            x1, y1, x2, y2 = strongest.bbox_xyxy
            area = ((x2 - x1) * (y2 - y1)) / (width * height)
            observation = source_from_box(
                camera_id=camera_id,
                class_name=class_name,
                bbox_xyxy=strongest.bbox_xyxy,
                confidence=strongest.confidence,
                image_width=width,
                image_height=height,
                captured_at=timestamp,
            )
            bucket = state.observations.setdefault((room_id, class_name), [])
            bucket.append(observation)
            cutoff = timestamp - timedelta(milliseconds=config.localization.window_ms)
            state.observations[(room_id, class_name)] = [
                item for item in bucket if item.captured_at >= cutoff
            ]
        evidence = tracker.update(timestamp=timestamp, confidence=confidence, bbox_area=area)
        if evidence is None:
            state.latest.pop(tracker_key, None)
        else:
            state.latest[tracker_key] = evidence
            if evidence.state == TemporalState.CONFIRMED and evidence.transitioned_from in {
                TemporalState.NORMAL,
                TemporalState.SUSPECT,
            }:
                just_confirmed = True
                confirmed_evidence[class_name] = evidence

    if not just_confirmed:
        if state.episode_open.get(room_id) and not _room_active(state, room_id):
            state.episode_open[room_id] = False
    elif not state.episode_open.get(room_id):
        fire_on = _class_confirmed(state, room_id, "fire")
        smoke_on = _class_confirmed(state, room_id, "smoke")
        if fire_on and smoke_on:
            alert_type = "FIRE_AND_SMOKE"
            locate_class = "fire"
        elif fire_on:
            alert_type = "FIRE"
            locate_class = "fire"
        else:
            alert_type = "SMOKE"
            locate_class = "smoke"
        sources = latest_in_window(
            state.observations.get((room_id, locate_class), []),
            timestamp,
            config.localization.window_ms,
        )
        pump_observations = []
        for bound_id in bound_camera_ids:
            evidence = state.latest.get((room_id, bound_id, locate_class))
            if evidence is None or evidence.state not in {TemporalState.SUSPECT, TemporalState.CONFIRMED}:
                continue
            pump_observations.append(
                {
                    "camera_id": bound_id,
                    "class_name": locate_class,
                    "score": evidence.score,
                    "effective_frames": evidence.effective_frames,
                    "duration_ms": evidence.duration_ms,
                }
            )
        frames = [state.frames[item] for item in bound_camera_ids if item in state.frames]
        started = confirmed_evidence.get(locate_class)
        on_alert(
            AlertDraft(
                room_id=room_id,
                alert_type=alert_type,
                started_at=started.first_seen_at if started is not None else timestamp,
                sources=sources,
                frames=frames,
                pump_observations=pump_observations,
            )
        )
        state.episode_open[room_id] = True

    return {
        "online": True,
        "width": width,
        "height": height,
        "states": {
            "fire": state.trackers[(room_id, camera_id, "fire")].state.value,
            "smoke": state.trackers[(room_id, camera_id, "smoke")].state.value,
        },
        "detections": [
            {
                "class_name": item.class_name,
                "confidence": item.confidence,
                "bbox": list(item.bbox_xyxy),
            }
            for item in kept
        ],
    }


def _class_confirmed(state: DetectionState, room_id: int, class_name: str) -> bool:
    return any(
        tracker.state == TemporalState.CONFIRMED
        for (item_room, _camera, item_class), tracker in state.trackers.items()
        if item_room == room_id and item_class == class_name
    )


def _room_active(state: DetectionState, room_id: int) -> bool:
    return any(
        tracker.state in {TemporalState.SUSPECT, TemporalState.CONFIRMED}
        for (item_room, _camera, _class_name), tracker in state.trackers.items()
        if item_room == room_id
    )
