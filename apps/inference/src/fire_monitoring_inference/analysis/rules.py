from __future__ import annotations

import json
from pathlib import Path

SCENE_TYPES = (
    "classroom",
    "laboratory",
    "electrical_room",
    "dormitory",
    "kitchen",
    "warehouse",
    "corridor",
)

_RULES: dict | None = None


def rules_path() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "config" / "fire_rules.json"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("config/fire_rules.json")


def load_rules() -> dict:
    global _RULES
    if _RULES is None:
        _RULES = json.loads(rules_path().read_text(encoding="utf-8"))
    return _RULES


def scene_label(scene: str) -> str:
    table = load_rules()["scenes"]
    if scene not in table:
        raise ValueError(f"unknown scene {scene}")
    return table[scene]["label"]


def _blocked(agent: str, forbidden: list[str]) -> bool:
    if agent in forbidden:
        return True
    return agent == "水" and "直流水" in forbidden


def _evidence_hits(evidence: dict) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    cause = evidence["suspected_cause"]
    if evidence["metal_powder"]:
        hits.append(("D", "看到金属粉末"))
    if evidence["oil_pan"] or cause == "cooking_oil":
        reason = "看到油锅" if evidence["oil_pan"] else "疑似烹饪油脂"
        hits.append(("F", reason))
    if evidence["liquid"] and not evidence["oil_pan"] and cause != "cooking_oil":
        hits.append(("B", "看到液体"))
    if cause == "lab_reagent":
        hits.append(("B", "疑似实验试剂"))
    if evidence["energized_equipment"] or cause == "electrical_short":
        reason = "看到带电设备" if evidence["energized_equipment"] else "疑似电气短路"
        hits.append(("E", reason))
    if evidence["burning_objects"] and not evidence["metal_powder"]:
        hits.append(("A", "可见固体燃烧物"))
    return hits


def _prior_hits(evidence: dict | None, configured_scene: str) -> list[tuple[str, str]]:
    scene = load_rules()["scenes"][configured_scene]
    label = scene["label"]
    hits: list[tuple[str, str]] = []
    for prior in scene["priors"]:
        if prior.get("always"):
            hits.append((prior["class"], f"{label}场景先验，默认按该类"))
            continue
        if evidence is None:
            continue
        cause = evidence["suspected_cause"]
        flagged = any(evidence[name] for name in prior.get("flags", []))
        if cause in prior.get("causes", []) or flagged:
            hits.append((prior["class"], f"{label}场景先验，提高该类"))
    return hits


def resolve(class_ids: list[str], reasons: dict[str, str] | None = None) -> dict:
    rules = load_rules()
    known = set(rules["classes"])
    unknown = [item for item in class_ids if item not in known]
    if unknown:
        raise ValueError(f"unknown fire class {unknown[0]}")
    order = rules["strictness"]
    selected = [item for item in order if item in set(class_ids)]
    reason_of = reasons or {}
    forbidden: list[str] = []
    recommended: list[str] = []
    actions: list[str] = []
    water = False
    details = []
    for class_id in selected:
        spec = rules["classes"][class_id]
        for item in spec["forbidden"]:
            if item not in forbidden:
                forbidden.append(item)
        if spec["water_prohibited"]:
            water = True
        for action in spec["actions"]:
            if action not in actions:
                actions.append(action)
        details.append(
            {
                "id": class_id,
                "name": spec["name"],
                "reason": reason_of.get(class_id, spec["name"]),
            }
        )
    for class_id in selected:
        for agent in rules["classes"][class_id]["recommended"]:
            if _blocked(agent, forbidden) or agent in recommended:
                continue
            recommended.append(agent)
    basis = [f"{item['reason']}，判为 {item['id']} 类（{item['name']}）" for item in details]
    if len(selected) > 1:
        basis.append("多类同时出现，禁止项取并集：" + "、".join(forbidden))
    elif forbidden:
        basis.append("禁止：" + "、".join(forbidden))
    for action in actions:
        basis.append(action)
    if recommended:
        basis.append("可用：" + "、".join(recommended))
    if not selected:
        basis.append("没有足够证据确定火灾类别")
    return {
        "classes": selected,
        "details": details,
        "recommended": recommended,
        "forbidden": forbidden,
        "actions": actions,
        "water_prohibited": water,
        "basis": basis,
    }


def classify(evidence: dict | None, configured_scene: str) -> dict:
    if configured_scene not in load_rules()["scenes"]:
        raise ValueError(f"unknown scene {configured_scene}")
    merged: dict[str, str] = {}
    if evidence is not None:
        for class_id, reason in _evidence_hits(evidence):
            merged.setdefault(class_id, reason)
    for class_id, reason in _prior_hits(evidence, configured_scene):
        merged.setdefault(class_id, reason)
    return resolve(list(merged), merged)


def sms_method(resolved: dict) -> str:
    rules = load_rules()
    limit = rules["sms_limit"]
    if not resolved["classes"]:
        text = rules["empty_sms"]
    else:
        text = rules["classes"][resolved["classes"][0]]["sms"]
        for action in resolved["actions"]:
            if action in text:
                continue
            longer = f"{action}，{text}"
            if len(longer) > limit:
                raise ValueError("sms method exceeds the variable limit")
            text = longer
    if len(text) > limit:
        raise ValueError("sms method exceeds the variable limit")
    return text


def oled_text(grade: str, resolved: dict) -> str:
    classes = "".join(resolved["classes"]) if resolved["classes"] else "未分类"
    water = "禁水" if resolved["water_prohibited"] else "可喷水"
    lines = [f"{grade} {classes}", water]
    if resolved["actions"]:
        lines.append(resolved["actions"][0])
    return "\n".join(lines)
