from __future__ import annotations

from .rules import load_rules

_ORDER = ["Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ"]


def _upgrade(grade: str) -> str:
    index = _ORDER.index(grade)
    return _ORDER[min(index + 1, len(_ORDER) - 1)]


def grade_incident(
    *,
    q_kw: float | None,
    growth_bin: str | None,
    dense_smoke: bool,
    people: bool,
    scene_risk: int,
    scene_label: str,
    spread_hits: list[dict],
) -> dict:
    rules = load_rules()["severity"]
    score = 0
    reasons: list[str] = []
    if q_kw is not None:
        matched = [band for band in rules["q_bands"] if q_kw >= band["min"]]
        if matched:
            band = matched[0]
            score += band["score"]
            reasons.append(band["reason"])
    if growth_bin is not None:
        score += rules["growth_scores"][growth_bin]
        reasons.append(rules["growth_reasons"][growth_bin])
    if dense_smoke:
        score += rules["dense_smoke"]["score"]
        reasons.append(rules["dense_smoke"]["reason"])
    if people:
        score += rules["people"]["score"]
        reasons.append(rules["people"]["reason"])
    if scene_risk:
        score += scene_risk
        reasons.append(f"场景风险：{scene_label}")
    grade = next(item["grade"] for item in rules["grades"] if score >= item["min_score"])
    if spread_hits:
        grade = _upgrade(grade)
        names = "、".join(dict.fromkeys(item["name"] for item in spread_hits))
        reasons.append(f"蔓延外推进入{names}，等级上调")
    if not reasons:
        reasons.append("未触发加分项")
    return {"grade": grade, "score": score, "reasons": reasons}
