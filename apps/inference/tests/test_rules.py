import pytest

from fire_monitoring_inference.analysis.rules import classify, resolve, sms_method


def evidence(**overrides):
    base = {
        "burning_objects": [{"frame_index": 1, "name": "纸", "evidence": "画面1桌面"}],
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
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "class_id,water,forbidden,recommended",
    [
        ("A", False, [], ["水", "泡沫", "ABC干粉"]),
        ("B", True, ["直流水"], ["泡沫", "抗溶泡沫", "干粉", "二氧化碳"]),
        ("C", False, [], ["干粉", "二氧化碳"]),
        ("D", True, ["水", "二氧化碳"], ["D类干粉", "干沙"]),
        ("E", True, ["水"], ["二氧化碳", "干粉"]),
        ("F", True, ["水"], ["锅盖或灭火毯", "F类灭火器"]),
    ],
)
def test_each_fire_class(class_id, water, forbidden, recommended):
    resolved = resolve([class_id])
    assert resolved["water_prohibited"] is water
    assert resolved["forbidden"] == forbidden
    assert resolved["recommended"] == recommended
    assert class_id in resolved["basis"][0]
    assert len(sms_method(resolved)) <= 35


@pytest.mark.parametrize(
    "classes,water,forbidden",
    [
        (["A", "E"], True, ["水"]),
        (["A", "B"], True, ["直流水"]),
        (["B", "D"], True, ["水", "二氧化碳", "直流水"]),
        (["D", "E"], True, ["水", "二氧化碳"]),
        (["E", "F"], True, ["水"]),
        (["A", "C"], False, []),
        (["A", "B", "C", "D", "E", "F"], True, ["水", "二氧化碳", "直流水"]),
    ],
)
def test_combined_classes_take_every_prohibition(classes, water, forbidden):
    resolved = resolve(classes)
    assert resolved["water_prohibited"] is water
    assert resolved["forbidden"] == forbidden
    if water:
        assert "水" not in resolved["recommended"]
    if "D" in classes:
        assert "二氧化碳" not in resolved["recommended"]
    assert len(sms_method(resolved)) <= 35


def test_energized_evidence_is_class_e_and_forbids_water():
    resolved = classify(
        evidence(energized_equipment=True, suspected_cause="electrical_short"),
        "classroom",
    )
    assert "E" in resolved["classes"]
    assert resolved["water_prohibited"] is True
    assert any("带电" in line for line in resolved["basis"])


def test_laboratory_unknown_raises_b_and_d_and_electrical_room_defaults_to_e():
    lab = classify(evidence(suspected_cause="unknown", burning_objects=[]), "laboratory")
    assert {"B", "D"} <= set(lab["classes"])
    assert lab["water_prohibited"] is True
    room = classify(None, "electrical_room")
    assert room["classes"] == ["E"]
    assert room["water_prohibited"] is True
    clear = classify(evidence(), "laboratory")
    assert clear["classes"] == ["A"]
    assert clear["water_prohibited"] is False


def test_cooking_oil_and_metal_powder_keep_their_own_classes():
    oil = classify(
        evidence(oil_pan=True, suspected_cause="cooking_oil", burning_objects=[]),
        "kitchen",
    )
    assert oil["classes"] == ["F"]
    metal = classify(evidence(metal_powder=True, burning_objects=[]), "laboratory")
    assert "D" in metal["classes"]
    assert "二氧化碳" in metal["forbidden"]
