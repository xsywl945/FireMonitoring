import json
from pathlib import Path

from fastapi.testclient import TestClient

from fire_monitoring.config import load_config
from fire_monitoring.db import make_engine
from fire_monitoring.evidence.store import MemoryStore
from fire_monitoring.main import create_app
from fire_monitoring.models import Alert, AlertEvent

EXAMPLE = Path(__file__).resolve().parents[3] / "config.example.json"
PACK = Path(__file__).resolve().parents[3] / "data" / "demo" / "synthetic-classroom"


def _app(tmp_path: Path, *, pump_run: bool = True):
    config = load_config(EXAMPLE)
    config.demo.enabled = True
    config.demo.pack = str(PACK)
    config.demo.hardware = "sim"
    config.demo.detector = "replay"
    config.demo.pump_run = pump_run
    config.pump.journal_path = str(tmp_path / "pump.sqlite3")
    config.suppression.gimbal_path = str(tmp_path / "gimbal.json")
    config.llm.enabled = False
    config.sms.enabled = False
    engine = make_engine(f"sqlite:///{tmp_path / 'demo.db'}")
    app = create_app(config, engine=engine, evidence=MemoryStore(), start_worker=False)
    return app


def _run(app, script: str) -> dict:
    player = app.state.demo.player
    player.start(script, 0)
    player.join(90)
    return app.state.demo.status()


def _kinds(status: dict) -> list[str]:
    return [item["kind"] for item in status["events"]]


def _fire_alert(app):
    session = app.state.session_factory()
    try:
        alerts = session.query(Alert).order_by(Alert.id).all()
        fire = [item for item in alerts if item.alert_type == "FIRE"]
        assert len(fire) == 1
        return fire[0], json.loads(fire[0].analysis_json), json.loads(fire[0].position_json)
    finally:
        session.close()


def test_mode_badge_is_public(tmp_path: Path) -> None:
    app = _app(tmp_path)
    with TestClient(app) as client:
        body = client.get("/api/v1/demo/mode").json()
    assert body["enabled"] is True
    assert body["label"] == "演示模式"
    assert body["synthetic"] is True


def test_three_scripts_follow_the_live_pipeline(tmp_path: Path) -> None:
    app = _app(tmp_path)
    try:
        full = _run(app, "full")
        kinds = _kinds(full)
        order = ["SUP_SUSPECTED", "SUP_CONFIRMED", "SUP_AIM", "SUP_PENDING", "SUP_SPRAY", "SUP_REVIEW", "SUP_OUT"]
        positions = [kinds.index(kind) for kind in order]
        assert positions == sorted(positions)
        _alert, analysis, position = _fire_alert(app)
        truth = app.state.demo.pack["scripts"]["full"]["fire_xyz"]
        error = sum((left - right) ** 2 for left, right in zip(position["xyz"], truth, strict=True)) ** 0.5
        assert position["status"] == "ESTIMATED"
        assert error < 0.25
        assert "A" in analysis["rules"]["classes"]
        assert analysis["water_prohibited"] is False
        assert analysis["cached"] is True
        assert analysis["synthetic_response"] is True
        assert "手写" in analysis["cache_note"]
        assert analysis["growth"]["mode"] == "heat_release"
        assert full["pump_run"] is True
        assert app.state.demo.pump.transport.device.running is False

        electrical = _run(app, "electrical")
        ekinds = _kinds(electrical)
        assert "SUP_SUSPECTED" in ekinds
        assert "SUP_SPRAY" not in ekinds
        assert electrical["block"] == "WATER_PROHIBITED"
        _alert, analysis, position = _fire_alert(app)
        truth = app.state.demo.pack["scripts"]["electrical"]["fire_xyz"]
        error = sum((left - right) ** 2 for left, right in zip(position["xyz"], truth, strict=True)) ** 0.5
        assert error < 0.25
        assert "E" in analysis["rules"]["classes"]
        assert analysis["water_prohibited"] is True
        assert "二氧化碳" in analysis["rules"]["recommended"]
        assert "先断电" in analysis["rules"]["actions"]
        assert analysis["cached"] is True

        person = _run(app, "person")
        pkinds = _kinds(person)
        assert "SUP_SPRAY" not in pkinds
        assert person["block"] == "PERSON"
        _alert, analysis, position = _fire_alert(app)
        truth = app.state.demo.pack["scripts"]["person"]["fire_xyz"]
        error = sum((left - right) ** 2 for left, right in zip(position["xyz"], truth, strict=True)) ** 0.5
        assert error < 0.25
        assert "A" in analysis["rules"]["classes"]
        assert analysis["evidence"]["person_count"] == 1
        assert analysis["cached"] is True
        assert person["label"] == "演示模式"
    finally:
        app.state.demo.close()


def test_pump_run_can_be_disabled(tmp_path: Path) -> None:
    app = _app(tmp_path, pump_run=False)
    try:
        status = _run(app, "full")
        assert status["pump_run"] is False
        assert "SUP_SPRAY" in _kinds(status)
        records = app.state.demo.pump.snapshot()["records"]
        assert records == [] or all(item["status"] != "RUNNING" for item in records)
        assert app.state.demo.pump.transport.device.running is False
    finally:
        app.state.demo.close()


def test_operator_cannot_start_a_script(tmp_path: Path) -> None:
    app = _app(tmp_path)
    with TestClient(app) as client:
        token = client.post("/api/v1/auth/login", json={"username": "duty", "password": "123456"}).json()[
            "access_token"
        ]
        denied = client.post(
            "/api/v1/demo/start",
            headers={"Authorization": f"Bearer {token}"},
            json={"script": "full", "speed": 0},
        )
        assert denied.status_code == 403
        admin = client.post("/api/v1/auth/login", json={"username": "admin", "password": "123456"}).json()[
            "access_token"
        ]
        started = client.post(
            "/api/v1/demo/start",
            headers={"Authorization": f"Bearer {admin}"},
            json={"script": "electrical", "speed": 0},
        )
        assert started.status_code == 200
        assert started.json()["script"] == "electrical"
        app.state.demo.player.join(90)
        reset = client.post("/api/v1/demo/reset", headers={"Authorization": f"Bearer {admin}"})
        assert reset.status_code == 200
        assert reset.json()["script"] is None
        session = app.state.session_factory()
        try:
            assert session.query(AlertEvent).count() == 0
        finally:
            session.close()
