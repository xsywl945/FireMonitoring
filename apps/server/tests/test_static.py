from pathlib import Path

from fastapi.testclient import TestClient

from fire_monitoring.config import load_config
from fire_monitoring.db import make_engine
from fire_monitoring.evidence.store import MemoryStore
from fire_monitoring.main import create_app
from fire_monitoring.web import mount_spa

EXAMPLE = Path(__file__).resolve().parents[3] / "config.example.json"


def test_static_frontend_does_not_hide_the_api(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>火情监控</title>", encoding="utf-8")
    (assets / "app.js").write_text("console.log(1)\n", encoding="utf-8")
    (dist / "favicon.ico").write_bytes(b"ico")
    config = load_config(EXAMPLE)
    app = create_app(
        config,
        engine=make_engine(f"sqlite:///{tmp_path / 'api.db'}"),
        evidence=MemoryStore(),
        start_worker=False,
    )
    mount_spa(app, dist)
    client = TestClient(app)
    assert client.get("/").text.startswith("<!doctype html>")
    assert client.get("/rooms").text.startswith("<!doctype html>")
    assert client.get("/assets/app.js").text == "console.log(1)\n"
    assert client.get("/favicon.ico").content == b"ico"
    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "123456"})
    assert login.status_code == 200
    missing = client.get("/no-such-page")
    assert missing.status_code == 200
    assert missing.text.startswith("<!doctype html>")
