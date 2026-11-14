from __future__ import annotations

from .growth import fit_area, fit_heat_release
from .rules import classify, load_rules, oled_text, scene_label, sms_method
from .severity import grade_incident
from .size import summarize_views

PROMPT_VERSION = "fire-evidence-v4"


def _growth(prepared: dict) -> dict:
    heat = prepared["heat_samples"]
    if heat:
        span = heat[-1][0] - heat[0][0]
        if span >= 10:
            return fit_heat_release(heat)
        return {
            "mode": "insufficient",
            "reason": "已有火点深度，热释放速率样本不足 10 秒",
            "samples": [{"t": t - heat[0][0], "q": q} for t, q in heat],
        }
    area = prepared["area_samples"]
    if len(area) >= 2 and area[-1][0] > area[0][0]:
        return fit_area(area)
    return {"mode": "insufficient", "reason": "没有可用于增长拟合的样本"}


def _texts(location: str, grade: str, resolved: dict) -> dict:
    limit = load_rules()["sms_limit"]
    if len(location) > limit:
        raise ValueError("sms location exceeds the variable limit")
    level = f"{grade}级"
    method = sms_method(resolved)
    if len(level) > limit:
        raise ValueError("sms level exceeds the variable limit")
    return {
        "sms_location": location,
        "sms_level": level,
        "sms_method": method,
        "oled": oled_text(grade, resolved),
    }


def assess(
    call: dict | None,
    *,
    configured_scene: str,
    location: str,
    prepared: dict,
    spread: dict | None,
    observed_scene: str | None = None,
) -> dict:
    evidence = None
    status = "FAILED"
    provider = "dashscope"
    model = ""
    prompt_version = PROMPT_VERSION
    error_code = "VLM_DISABLED"
    if call is not None:
        status = call["status"]
        provider = call["provider"]
        model = call["model"]
        prompt_version = call["prompt_version"]
        error_code = call.get("error_code")
        if status == "SUCCEEDED":
            evidence = call["evidence"]
            error_code = None
    resolved = classify(evidence, configured_scene)
    size = summarize_views(prepared["views"]) if prepared["views"] else None
    growth = _growth(prepared)
    if spread is None:
        spread_doc = {"status": "UNOBSERVABLE", "hits": []}
    else:
        spread_doc = spread
    scene = load_rules()["scenes"][configured_scene]
    observed = observed_scene or (None if evidence is None else evidence["scene_type"])
    level = grade_incident(
        q_kw=None if size is None else size["q_kw"],
        growth_bin=growth.get("bin"),
        dense_smoke=evidence is not None and evidence["smoke_density"] == "dense",
        people=evidence is not None and evidence["person_count"] > 0,
        scene_risk=scene["risk"],
        scene_label=scene["label"],
        spread_hits=spread_doc.get("hits", []),
    )
    visible_fire = evidence is not None and bool(evidence["burning_objects"])
    visible_smoke = evidence is not None and evidence["smoke_density"] in {"light", "dense"}
    return {
        "status": status,
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "error_code": error_code,
        "has_visible_fire": visible_fire,
        "has_visible_smoke": visible_smoke,
        "water_prohibited": resolved["water_prohibited"],
        "evidence": evidence,
        "rules": resolved,
        "scene": {
            "configured": configured_scene,
            "configured_label": scene_label(configured_scene),
            "observed": observed,
            "observed_label": None if observed is None else scene_label(observed),
            "mismatch": observed is not None and observed != configured_scene,
        },
        "size": size,
        "growth": growth,
        "level": level,
        "spread": spread_doc,
        "texts": _texts(location, level["grade"], resolved),
    }
