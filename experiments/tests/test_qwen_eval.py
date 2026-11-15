import json
from pathlib import Path

import pytest

from experiments.qwen_eval import main

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "experiments" / "examples" / "qwen_manifest.csv"
FIXTURES = ROOT / "experiments" / "examples" / "qwen_fixtures.json"


def test_fixture_comparison_is_not_a_live_call(tmp_path: Path):
    out = tmp_path / "out"
    main(["--manifest", str(MANIFEST), "--fixtures", str(FIXTURES), "--out", str(out)])
    payload = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert payload["data"] == "固定假响应"
    direct = payload["summary"]["direct"]
    evidence = payload["summary"]["evidence"]
    assert direct["unsafe_advice_rate"] == 1
    assert evidence["unsafe_advice_rate"] == 0
    assert evidence["class_accuracy"] > direct["class_accuracy"]
    assert direct["cost_cny"] is None
    assert (out / "qwen-compare.png").is_file()


def test_missing_fixture_row_exits(tmp_path: Path):
    manifest = tmp_path / "manifest.csv"
    manifest.write_text("path,label\nmissing.jpg,A\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="假响应缺少"):
        main(
            [
                "--manifest",
                str(manifest),
                "--fixtures",
                str(FIXTURES),
                "--out",
                str(tmp_path / "out"),
            ]
        )


def test_live_missing_image_does_not_print_the_key(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    key = "SECRET-KEY-DO-NOT-PRINT"
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "llm": {
                    "base_url": "https://example.invalid/v1",
                    "model": "qwen3.7-plus",
                    "api_key": key,
                }
            }
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.csv"
    manifest.write_text("path,label\nmissing.jpg,A\n", encoding="utf-8")
    with pytest.raises(SystemExit) as caught:
        main(
            [
                "--manifest",
                str(manifest),
                "--live",
                "--config",
                str(config),
                "--out",
                str(tmp_path / "out"),
            ]
        )
    captured = capsys.readouterr()
    assert key not in captured.out
    assert key not in captured.err
    assert key not in str(caught.value)
