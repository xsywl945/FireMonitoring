from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..analysis.rules import load_rules
from .place import place_name, spoken_room

PENDING_VOICE = "喷头即将喷水，请远离"
EXTINGUISHED_VOICE = "明火已扑灭，请现场确认"
ESTOP_VOICE = "系统已急停"
PERSON_VOICE = "附近有人，请立即撤离"
PROHIBITED = {
    "E": "带电火灾，禁止用水，请使用二氧化碳灭火器并切断电源",
    "D": "金属火灾，禁止用水，请使用D类干粉或干沙",
    "F": "油脂火灾，禁止用水，请用锅盖或灭火毯覆盖",
    "B": "液体火灾，禁止直流水，请使用泡沫或干粉灭火器",
}


class Speaker(Protocol):
    muted: bool

    def say(self, text: str) -> None: ...


class MemorySpeaker:
    def __init__(self) -> None:
        self.muted = False
        self.lines: list[str] = []

    def say(self, text: str) -> None:
        if self.muted:
            return
        self.lines.append(text)


class FileSpeaker:
    """Host-side stand-in. Swap this class for an offline TTS player."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.muted = False
        self.lines: list[str] = []

    def say(self, text: str) -> None:
        if self.muted:
            return
        self.lines.append(text)
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / "last.txt").write_text(text, encoding="utf-8")


def smoke_voice(room_name: str) -> str:
    return f"{spoken_room(room_name)}疑似烟雾，请值班人员查看"


def fire_voice(room_name: str, xyz, room_size: tuple[float, float], grade: str) -> str:
    place = place_name(float(xyz[0]), float(xyz[1]), room_size[0], room_size[1])
    return f"{spoken_room(room_name)}{place}发现明火，等级{grade}，请立即撤离"


def prohibited_voice(resolved: dict) -> str:
    if not resolved["classes"]:
        raise ValueError("water is prohibited without a fire class")
    class_id = resolved["classes"][0]
    if class_id in PROHIBITED:
        return PROHIBITED[class_id]
    spec = load_rules()["classes"][class_id]
    agents = "、".join(spec["recommended"])
    text = f"{spec['name']}火灾，禁止用水，请使用{agents}"
    if spec["actions"]:
        text += "并" + "、".join(spec["actions"])
    return text
