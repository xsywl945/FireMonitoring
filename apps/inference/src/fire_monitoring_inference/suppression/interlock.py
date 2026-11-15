from __future__ import annotations

import numpy as np

from ..analysis.rules import classify
from .coverage import cover_probability, max_std
from .persons import nearest_distance


def resolved_rules(scene: str, analysis: dict | None) -> dict:
    evidence = None
    if analysis is not None and analysis.get("status") == "SUCCEEDED":
        evidence = analysis.get("evidence")
    return classify(evidence, scene)


def vlm_accepts(analysis: dict | None) -> bool:
    return bool(
        analysis is not None
        and analysis.get("status") == "SUCCEEDED"
        and (analysis.get("has_visible_fire") or analysis.get("has_visible_smoke"))
    )


def spray_block(shot, aim, probability: float | None, *, sweeping: bool) -> str | None:
    if shot.cancelled:
        return "CAMERA_STOPPED"
    if not 0 <= shot.evidence_age_s <= shot.max_evidence_age_s:
        return "STALE_EVIDENCE"
    if not shot.pump_enabled:
        return "PUMP_DISABLED"
    if not shot.zone_ok:
        return "ZONE_NOT_COVERED"
    if not shot.local_fire:
        return "LOCAL_FIRE_NOT_CONFIRMED"
    if resolved_rules(shot.scene, shot.analysis)["water_prohibited"]:
        return "WATER_PROHIBITED"
    if shot.require_vlm and not vlm_accepts(shot.analysis):
        return "VLM_NOT_CONFIRMED"
    position = shot.position
    if position is None or position.get("status") != "ESTIMATED":
        return "NOT_LOCALIZED"
    if max_std(position["covariance"]) >= shot.max_std_m:
        return "COVARIANCE"
    if aim is None:
        return "OUT_OF_RANGE"
    fire = position["xyz"]
    distance = nearest_distance(fire, shot.persons)
    if distance is not None and distance < shot.person_distance_m:
        return "PERSON"
    if not shot.heartbeat_ok:
        return "HEARTBEAT"
    if not shot.cooldown_elapsed:
        return "COOLDOWN"
    if not sweeping and (probability is None or probability < shot.cover_threshold):
        return "COVERAGE"
    return None


def aim_probability(shot, aim) -> float | None:
    position = shot.position
    if position is None or position.get("status") != "ESTIMATED" or aim is None:
        return None
    return cover_probability(np.asarray(position["covariance"], dtype=float), shot.cover_radius_m)
