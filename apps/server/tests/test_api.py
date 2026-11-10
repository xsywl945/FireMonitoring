import json
from pathlib import Path

from fastapi.testclient import TestClient

from fire_monitoring.config import load_config
from fire_monitoring.db import make_engine
from fire_monitoring.evidence.store import MemoryStore
from fire_monitoring.main import create_app

EXAMPLE = Path(__file__).resolve().parents[3] / "config.example.json"


def _client(tmp_path: Path) -> TestClient:
    config = load_config(EXAMPLE)
    engine = make_engine(f"sqlite:///{tmp_path / 'api.db'}")
    app = create_app(
        config,
        engine=engine,
        evidence=MemoryStore(),
        start_worker=False,
    )
    return TestClient(app)


def _auth(client: TestClient, username: str, password: str = "123456") -> dict:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_login_bindings_calibration_and_masked_config(tmp_path: Path) -> None:
    client = _client(tmp_path)
    admin = _auth(client, "admin")
    duty = _auth(client, "duty")
    denied = client.get("/api/v1/config", headers=duty)
    assert denied.status_code == 403
    masked = client.get("/api/v1/config", headers=admin)
    assert masked.status_code == 200
    assert "change-this-jwt-secret-to-a-long-random-string" not in masked.text
    assert masked.json()["model"]["thresholds"] == {"fire": 0.3, "smoke": 0.35}

    room = client.post(
        "/api/v1/rooms",
        headers=admin,
        json={"name": "101", "scene_type": "classroom"},
    )
    assert room.status_code == 200
    room_id = room.json()["id"]
    camera_ids = []
    for index in range(4):
        created = client.post(
            "/api/v1/cameras",
            headers=admin,
            json={
                "name": f"摄像头{index + 1}",
                "source_type": "USB" if index < 3 else "RTSP",
                "source_uri": f"USB Camera {index}" if index < 3 else "rtsp://10.0.0.8/live",
                "stream_key": f"cam{index + 1}",
                "target_fps": None,
            },
        )
        assert created.status_code == 200
        assert created.json()["target_fps"] == 15
        camera_ids.append(created.json()["id"])

    bound = client.put(
        f"/api/v1/rooms/{room_id}/cameras",
        headers=admin,
        json={"camera_ids": camera_ids},
    )
    assert bound.status_code == 200
    assert [item["slot"] for item in bound.json()["cameras"]] == [1, 2, 3, 4]
    extra = client.put(
        f"/api/v1/rooms/{room_id}/cameras",
        headers=admin,
        json={"camera_ids": camera_ids + [camera_ids[0]]},
    )
    assert extra.status_code == 422

    calibration = {
        "intrinsics": [[800, 0, 320], [0, 800, 240], [0, 0, 1]],
        "distortion": [0, 0, 0, 0, 0],
        "landmarks": [
            {"world_m": [0, 0, 0], "pixel": [10, 10]},
            {"world_m": [1, 0, 0], "pixel": [100, 10]},
            {"world_m": [1, 1, 0], "pixel": [100, 100]},
            {"world_m": [0, 1, 0], "pixel": [10, 100]},
        ],
    }
    saved = client.put(
        f"/api/v1/cameras/{camera_ids[0]}/calibration",
        headers=admin,
        json=calibration,
    )
    assert saved.status_code == 200
    assert len(saved.json()["calibration"]["landmarks"]) == 4
    short = client.put(
        f"/api/v1/cameras/{camera_ids[0]}/calibration",
        headers=admin,
        json={**calibration, "landmarks": calibration["landmarks"][:3]},
    )
    assert short.status_code == 422

    plan = client.post(
        f"/api/v1/rooms/{room_id}/floor-plan",
        headers=admin,
        data={
            "origin_x": 10,
            "origin_y": 20,
            "meters_per_pixel": 0.05,
            "world_x": 0,
            "world_y": 0,
        },
        files={"file": ("plan.png", b"png-bytes", "image/png")},
    )
    assert plan.status_code == 200
    assert plan.json()["floor_plan"]["meters_per_pixel"] == 0.05
    image = client.get(f"/api/v1/rooms/{room_id}/floor-plan", headers=duty)
    assert image.status_code == 200
    assert image.content == b"png-bytes"

    listed = client.get("/api/v1/rooms", headers=duty)
    assert listed.status_code == 200
    assert listed.json()[0]["cameras"][0]["calibrated"] is True
