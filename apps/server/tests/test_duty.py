import csv
import json
from datetime import UTC, datetime, timedelta
from io import BytesIO, StringIO
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import select

from fire_monitoring.auth.deps import iso
from fire_monitoring.auth.security import password_matches
from fire_monitoring.config import load_config
from fire_monitoring.db import make_engine
from fire_monitoring.evidence.store import MemoryStore
from fire_monitoring.main import create_app
from fire_monitoring.models import Alert, AlertEvent, AlertFrame, Room, User

EXAMPLE = Path(__file__).resolve().parents[3] / "config.example.json"
STATUS = {
    "OPEN": "待处置",
    "ACKNOWLEDGED": "已确认",
    "FALSE_ALARM": "误报",
    "CLOSED": "已结案",
}


def _client(tmp_path: Path, *, engine=None, config_path: Path | None = None) -> TestClient:
    config = load_config(EXAMPLE)
    engine = engine or make_engine(f"sqlite:///{tmp_path / 'duty.db'}")
    app = create_app(
        config,
        engine=engine,
        evidence=MemoryStore(),
        start_worker=False,
        config_path=config_path,
    )
    return TestClient(app)


def _auth(client: TestClient, username: str, password: str = "123456") -> dict:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _jpeg(value: int) -> bytes:
    ok, encoded = cv2.imencode(".jpg", np.full((24, 32, 3), value, np.uint8))
    assert ok
    return encoded.tobytes()


def _png() -> bytes:
    ok, encoded = cv2.imencode(".png", np.full((60, 80, 3), 240, np.uint8))
    assert ok
    return encoded.tobytes()


def _add_alert(client: TestClient, room_id: int, *, started_at: datetime, level: str, fire_class: str) -> int:
    session = client.app.state.session_factory()
    alert = Alert(
        room_id=room_id,
        alert_type="FIRE",
        started_at=started_at,
        observations_json="[]",
        status="OPEN",
        level=level,
        fire_classes=fire_class,
        position_json=json.dumps(
            {"status": "ESTIMATED", "xyz": [0.2, 0.2, 0], "support_camera_ids": [1]}
        ),
        analysis_json=json.dumps(
            {
                "status": "SUCCEEDED",
                "level": {"grade": level, "score": 2, "reasons": ["明火持续"]},
                "rules": {
                    "classes": fire_class.split(","),
                    "details": [{"id": fire_class, "name": "固体物质火灾", "reason": "纸张"}],
                    "recommended": ["水"],
                    "forbidden": ["二氧化碳灭火器"],
                    "actions": [],
                    "basis": [],
                },
                "evidence": {
                    "burning_objects": [{"frame_index": 1, "name": "纸张", "evidence": "桌面"}],
                },
                "spread": {
                    "status": "ESTIMATED",
                    "now": [[0, 0], [1, 0], [1, 1]],
                    "horizon_30s": [[0, 0], [2, 0], [2, 2]],
                    "horizon_60s": [[0, 0], [3, 0], [3, 3]],
                },
            },
            ensure_ascii=False,
        ),
    )
    session.add(alert)
    session.flush()
    for camera_id in range(1, 5):
        key = f"alerts/{alert.id}/{camera_id}.jpg"
        client.app.state.evidence.put(key, _jpeg(40 * camera_id), "image/jpeg")
        session.add(
            AlertFrame(
                alert_id=alert.id,
                camera_id=camera_id,
                object_key=key,
                captured_at=started_at,
            )
        )
    session.add(
        AlertEvent(
            room_id=room_id,
            alert_id=alert.id,
            kind="CONFIRMED",
            detail_json=json.dumps({"room_name": "101"}),
            occurred_at=started_at,
        )
    )
    session.commit()
    alert_id = alert.id
    session.close()
    return alert_id


def test_operator_cannot_manage_users_or_config(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    client = _client(tmp_path, config_path=path)
    admin = _auth(client, "admin")
    duty = _auth(client, "duty")

    assert client.get("/api/v1/users", headers=duty).status_code == 403
    assert client.post(
        "/api/v1/users",
        headers=duty,
        json={"username": "new", "password": "secret", "display_name": "新值班", "role": "operator"},
    ).status_code == 403
    assert client.patch("/api/v1/users/1", headers=duty, json={"role": "operator"}).status_code == 403
    assert client.delete("/api/v1/users/1", headers=duty).status_code == 403
    denied = client.put("/api/v1/config", headers=duty, json={"cameras": {"default_fps": 9}})
    assert denied.status_code == 403

    created = client.post(
        "/api/v1/users",
        headers=admin,
        json={"username": "new", "password": "secret", "display_name": "新值班", "role": "operator"},
    )
    assert created.status_code == 200
    user_id = created.json()["id"]
    assert "password" not in created.json()
    session = client.app.state.session_factory()
    stored = session.get(User, user_id)
    assert stored.password_hash != "secret"
    assert password_matches("secret", stored.password_hash)
    session.close()
    assert _auth(client, "new", "secret")

    renamed = client.patch(
        f"/api/v1/users/{user_id}",
        headers=admin,
        json={"role": "admin", "password": "reset-pass", "display_name": "已改"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["role"] == "admin"
    assert client.post(
        "/api/v1/auth/login", json={"username": "new", "password": "secret"}
    ).status_code == 401
    assert _auth(client, "new", "reset-pass")

    assert client.delete(f"/api/v1/users/{user_id}", headers=admin).status_code == 200
    assert client.post(
        "/api/v1/auth/login", json={"username": "new", "password": "reset-pass"}
    ).status_code == 401
    self_delete = client.delete("/api/v1/users/1", headers=admin)
    assert self_delete.status_code == 409

    public = client.get("/api/v1/config", headers=admin)
    assert public.status_code == 200
    body = public.json()
    assert "password" not in body["database"]
    assert "users" not in body["auth"]
    assert "jwt_secret" not in body["auth"]
    assert "api_key" not in body["llm"]
    saved = client.put("/api/v1/config", headers=admin, json={"cameras": {"default_fps": 12}})
    assert saved.status_code == 200
    assert saved.json()["restart_required"] is True
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["cameras"]["default_fps"] == 12
    assert written["database"]["password"] == "change-me"
    assert written["auth"]["jwt_secret"].startswith("change-this")
    assert client.app.state.config.cameras.default_fps == 15
    rejected = client.put(
        "/api/v1/config", headers=admin, json={"database": {"password": "changed"}}
    )
    assert rejected.status_code == 422
    assert json.loads(path.read_text(encoding="utf-8"))["database"]["password"] == "change-me"


def test_restart_keeps_password_changed_in_the_database(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'users.db'}")
    with _client(tmp_path, engine=engine) as first:
        admin = _auth(first, "admin")
        duty_id = next(item["id"] for item in first.get("/api/v1/users", headers=admin).json() if item["username"] == "duty")
        changed = first.patch(f"/api/v1/users/{duty_id}", headers=admin, json={"password": "desk-pass"})
        assert changed.status_code == 200
    with _client(tmp_path, engine=engine) as second:
        assert second.post(
            "/api/v1/auth/login", json={"username": "duty", "password": "123456"}
        ).status_code == 401
        assert second.post(
            "/api/v1/auth/login", json={"username": "duty", "password": "desk-pass"}
        ).status_code == 200


def test_disposition_transitions_history_csv_and_pdf(tmp_path: Path) -> None:
    client = _client(tmp_path)
    admin = _auth(client, "admin")
    duty = _auth(client, "duty")
    room = client.post(
        "/api/v1/rooms", headers=admin, json={"name": "101", "scene_type": "classroom"}
    ).json()
    other = client.post(
        "/api/v1/rooms", headers=admin, json={"name": "102", "scene_type": "laboratory"}
    ).json()
    plan = client.post(
        f"/api/v1/rooms/{room['id']}/floor-plan",
        headers=admin,
        data={
            "origin_x": 10,
            "origin_y": 10,
            "meters_per_pixel": 0.05,
            "world_x": 0,
            "world_y": 0,
        },
        files={"file": ("plan.png", _png(), "image/png")},
    )
    assert plan.status_code == 200
    now = datetime.now(UTC).replace(microsecond=0)
    recent = _add_alert(client, room["id"], started_at=now, level="Ⅱ", fire_class="A")
    older = _add_alert(
        client,
        other["id"],
        started_at=now - timedelta(days=2),
        level="Ⅲ",
        fire_class="B",
    )
    third = _add_alert(
        client,
        room["id"],
        started_at=now - timedelta(hours=2),
        level="Ⅱ",
        fire_class="A,E",
    )

    illegal = client.post(
        f"/api/v1/alerts/{recent}/disposition",
        headers=duty,
        json={"action": "close", "note": "还没确认"},
    )
    assert illegal.status_code == 409
    assert "不能执行" in illegal.json()["detail"]

    acknowledged = client.post(
        f"/api/v1/alerts/{recent}/disposition",
        headers=duty,
        json={"action": "acknowledge", "note": "已看到"},
    )
    assert acknowledged.status_code == 200
    assert acknowledged.json()["status"] == "ACKNOWLEDGED"
    assert acknowledged.json()["disposition"]["actor"] == "duty"
    assert acknowledged.json()["disposition"]["occurred_at"]
    repeat = client.post(
        f"/api/v1/alerts/{recent}/disposition",
        headers=duty,
        json={"action": "acknowledge", "note": ""},
    )
    assert repeat.status_code == 409
    closed = client.post(
        f"/api/v1/alerts/{recent}/disposition",
        headers=duty,
        json={"action": "close", "note": "现场熄灭"},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "CLOSED"
    assert client.post(
        f"/api/v1/alerts/{recent}/disposition",
        headers=duty,
        json={"action": "false_alarm", "note": ""},
    ).status_code == 409

    false_alarm = client.post(
        f"/api/v1/alerts/{older}/disposition",
        headers=duty,
        json={"action": "false_alarm", "note": "反光"},
    )
    assert false_alarm.status_code == 200
    assert false_alarm.json()["status"] == "FALSE_ALARM"

    detail = client.get(f"/api/v1/alerts/{recent}", headers=duty)
    assert detail.status_code == 200
    actions = [item["action"] for item in detail.json()["dispositions"]]
    assert actions == ["acknowledge", "close"]
    assert detail.json()["dispositions"][1]["note"] == "现场熄灭"
    assert detail.json()["status"] == "CLOSED"

    listed = client.get(
        "/api/v1/alerts",
        headers=duty,
        params={"room_id": room["id"], "level": "Ⅱ", "fire_class": "A", "page": 1, "page_size": 1},
    )
    assert listed.status_code == 200
    page = listed.json()
    assert page["total"] == 2
    assert len(page["items"]) == 1
    assert page["items"][0]["id"] == recent
    ranged = client.get(
        "/api/v1/alerts",
        headers=duty,
        params={"started_from": (now - timedelta(hours=1)).isoformat(), "status": "CLOSED"},
    )
    assert [item["id"] for item in ranged.json()["items"]] == [recent]
    by_class = client.get("/api/v1/alerts", headers=duty, params={"fire_class": "E"})
    assert [item["id"] for item in by_class.json()["items"]] == [third]

    exported = client.get(
        "/api/v1/alerts/export",
        headers=duty,
        params={"room_id": room["id"], "level": "Ⅱ"},
    )
    assert exported.status_code == 200
    parsed = list(csv.DictReader(StringIO(exported.content.decode("utf-8-sig"))))
    session = client.app.state.session_factory()
    rows = session.scalars(
        select(Alert)
        .where(Alert.room_id == room["id"], Alert.level == "Ⅱ")
        .order_by(Alert.started_at.desc(), Alert.id.desc())
    ).all()
    assert [int(item["编号"]) for item in parsed] == [row.id for row in rows]
    for item, row in zip(parsed, rows, strict=True):
        room_row = session.get(Room, row.room_id)
        assert item["教室"] == room_row.name
        assert item["等级"] == row.level
        assert item["火灾类别"] == row.fire_classes
        assert item["处置状态"] == STATUS[row.status]
        assert item["开始时间"] == iso(row.started_at)
    session.close()

    report = client.get(f"/api/v1/alerts/{recent}/report", headers=duty)
    assert report.status_code == 200
    assert report.headers["content-type"] == "application/pdf"
    reader = PdfReader(BytesIO(report.content))
    text = "".join((page.extract_text() or "") for page in reader.pages)
    compact = "".join(text.split())
    for needle in ("101", "纸张", "固体物质火灾", "水", "二氧化碳灭火器", "Ⅱ", "明火持续", "现场熄灭", "duty"):
        assert needle in compact
    images = [image for page in reader.pages for image in page.images]
    assert len(images) >= 4
