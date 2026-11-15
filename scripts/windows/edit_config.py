import json
import sys
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    command = sys.argv[1]
    if command == "demo":
        data = load(Path(sys.argv[2]))
        data["demo"]["enabled"] = True
        data["demo"]["hardware"] = "sim"
        data["demo"]["detector"] = "replay"
        data["pump"]["enabled"] = False
        data["panel"]["enabled"] = False
        dump(Path(sys.argv[3]), data)
        return
    if command == "tools":
        path = Path(sys.argv[2])
        data = load(path)
        mediamtx = sys.argv[3]
        ffmpeg = sys.argv[4]
        if mediamtx and data["mediamtx"]["mediamtx_path"] == "mediamtx":
            data["mediamtx"]["mediamtx_path"] = mediamtx
        if ffmpeg and data["mediamtx"]["ffmpeg_path"] == "ffmpeg":
            data["mediamtx"]["ffmpeg_path"] = ffmpeg
        dump(path, data)
        return
    raise SystemExit(f"未知命令：{command}")


if __name__ == "__main__":
    main()
