import json
import re
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient
from fire_monitoring.calibration.extrinsics import (
    detect_control_points,
    fit_extrinsics,
    landmarks_from_points,
)
from fire_monitoring.calibration.health import assess_frame
from fire_monitoring.calibration.intrinsics import calibrate_charuco
from fire_monitoring.calibration.layout import charuco_page, marker_page, rasterize
from fire_monitoring.calibration.pdf import charuco_pdf, marker_pdf
from fire_monitoring.calibration.spec import CONTROL_IDS, charuco_board, paper
from fire_monitoring.config import load_config
from fire_monitoring.db import make_engine
from fire_monitoring.detection.ingest import FrameShot
from fire_monitoring.evidence.store import MemoryStore
from fire_monitoring.localization.observe import locate_position, write_manifest
from fire_monitoring.main import create_app
from fire_monitoring.models import Camera, Room, RoomCamera

EXAMPLE = Path(__file__).resolve().parents[3] / "config.example.json"
MM = 72 / 25.4


def _client(tmp_path: Path) -> TestClient:
    config = load_config(EXAMPLE)
    engine = make_engine(f"sqlite:///{tmp_path / 'calibration.db'}")
    app = create_app(config, engine=engine, evidence=MemoryStore(), start_worker=False)
    return TestClient(app)


def _auth(client: TestClient) -> dict:
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "123456"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _page_box(payload: bytes) -> tuple[float, float]:
    match = re.search(rb"/MediaBox\s*\[([^\]]+)\]", payload)
    assert match is not None
    parts = match.group(1).split()
    return float(parts[2]), float(parts[3])


def _png(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return encoded.tobytes()


def test_printed_pages_have_exact_paper_size_and_ids() -> None:
    expected = {"a4": (210.0, 297.0), "a3": (297.0, 420.0)}
    for name, (width_mm, height_mm) in expected.items():
        charuco = charuco_pdf(name)
        markers = marker_pdf(name)
        for payload, (page_w, page_h) in (
            (charuco, expected[name]),
            (markers, expected[name]),
        ):
            box_w, box_h = _page_box(payload)
            assert abs(box_w - page_w * MM) < 0.2
            assert abs(box_h - page_h * MM) < 0.2
        assert b"PRINT 100%" in charuco
        assert f"square {paper('charuco', name).square_mm:.2f} mm".encode() in charuco
        assert b"100 mm" in charuco
        for marker_id in CONTROL_IDS:
            assert str(marker_id).encode() in markers
        page = charuco_page(name)
        bars = [item for item in page.rects if abs(item.w_mm - 100.0) < 1e-9]
        assert len(bars) == 1
        assert abs(page.width_mm - width_mm) < 1e-9
        assert abs(page.height_mm - height_mm) < 1e-9


def test_rasterized_sheets_match_opencv_boards() -> None:
    for name, count in (("a4", 20), ("a3", 35)):
        image = rasterize(charuco_page(name), 4)
        detector = cv2.aruco.ArucoDetector(
            cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50),
            cv2.aruco.DetectorParameters(),
        )
        _corners, ids, _rejected = detector.detectMarkers(image)
        assert ids is not None
        assert set(int(item) for item in ids.ravel()) == set(range(count))
        board = charuco_board(name)
        charuco = cv2.aruco.CharucoDetector(board)
        corners, charuco_ids, _marker_corners, _marker_ids = charuco.detectBoard(image)
        assert charuco_ids is not None and len(charuco_ids) >= 8
        obj, _img = board.matchImagePoints(corners, charuco_ids)
        square_m = paper("charuco", name).square_mm / 1000
        assert np.max(np.abs(obj.reshape(-1, 3)[:, :2] / square_m - np.round(obj.reshape(-1, 3)[:, :2] / square_m))) < 1e-3
    for name in ("a4", "a3"):
        image = rasterize(marker_page(name), 3)
        detector = cv2.aruco.ArucoDetector(
            cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50),
            cv2.aruco.DetectorParameters(),
        )
        _corners, ids, _rejected = detector.detectMarkers(image)
        assert ids is not None
        assert set(int(item) for item in ids.ravel()) == set(CONTROL_IDS)


def _render_charuco_views(name: str = "a4"):
    spec = paper("charuco", name)
    board = charuco_board(name)
    square = spec.square_mm / 1000
    width_m = spec.squares[0] * square
    height_m = spec.squares[1] * square
    ppm = 7000
    board_image = board.generateImage((int(round(width_m * ppm)), int(round(height_m * ppm))))
    board_h, board_w = board_image.shape[:2]
    matrix = np.array([[900.0, 0, 640.0], [0, 910.0, 360.0], [0, 0, 1.0]])
    distortion = np.array([-0.22, 0.0, 0.0, 0.0, 0.0])
    size = (1280, 720)
    center = np.array([width_m / 2, height_m / 2, 0.0])
    images = []
    for yaw_deg, pitch_deg, shift_x, shift_y, distance in (
        (0, 0, 0.0, 0.0, 0.30),
        (0, 0, -0.18, 0.0, 0.34),
        (0, 0, 0.18, 0.0, 0.34),
        (0, 0, 0.0, 0.04, 0.40),
        (18, 0, -0.10, 0.0, 0.34),
        (-18, 0, 0.10, 0.0, 0.34),
        (0, 14, -0.12, 0.0, 0.36),
        (0, -14, 0.12, 0.0, 0.36),
        (16, 12, 0.0, 0.0, 0.38),
        (-16, -12, 0.0, 0.0, 0.38),
        (10, -10, -0.16, 0.02, 0.33),
        (-10, 10, 0.16, -0.02, 0.33),
    ):
        yaw = np.radians(yaw_deg)
        pitch = np.radians(pitch_deg)
        rotation = cv2.Rodrigues(np.array([pitch, yaw, 0.0]))[0]
        translation = np.array([shift_x, shift_y, distance]) - rotation @ center
        rvec = cv2.Rodrigues(rotation)[0]
        source = np.array([[0, 0], [board_w, 0], [board_w, board_h], [0, board_h]], np.float32)
        corners = np.array(
            [[0, 0, 0], [width_m, 0, 0], [width_m, height_m, 0], [0, height_m, 0]],
            np.float64,
        )
        projected, _ = cv2.projectPoints(corners, rvec, translation, matrix, np.zeros(5))
        homography = cv2.getPerspectiveTransform(source, projected.reshape(4, 2).astype(np.float32))
        undistorted = cv2.warpPerspective(board_image, homography, size, flags=cv2.INTER_LINEAR, borderValue=255)
        height, width = undistorted.shape[:2]
        xs, ys = np.meshgrid(np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))
        points = np.stack([xs, ys], axis=-1).reshape(-1, 1, 2)
        mapped = cv2.undistortPoints(points, matrix, distortion, P=matrix).reshape(height, width, 2)
        images.append(
            cv2.remap(
                undistorted,
                mapped[..., 0],
                mapped[..., 1],
                cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=255,
            )
        )
    return images, matrix, distortion


def test_synthetic_charuco_recovers_known_intrinsics() -> None:
    images, matrix, distortion = _render_charuco_views()
    result = calibrate_charuco(images, "a4")
    assert result.rms < 0.5
    assert abs(result.intrinsics[0][0] - matrix[0, 0]) < 6
    assert abs(result.intrinsics[1][1] - matrix[1, 1]) < 6
    assert abs(result.intrinsics[0][2] - matrix[0, 2]) < 5
    assert abs(result.intrinsics[1][2] - matrix[1, 2]) < 5
    assert abs(result.distortion[0] - distortion[0]) < 0.02
    assert abs(result.distortion[1] - distortion[1]) < 0.02
    assert abs(result.distortion[2]) < 0.002
    assert abs(result.distortion[3]) < 0.002
    assert result.distortion[4] == 0.0
    try:
        calibrate_charuco(images[:2], "a4")
    except ValueError as exc:
        assert "至少需要" in str(exc)
    else:
        raise AssertionError("too few views were accepted")


def _marker_scene(matrix=None, distortion=None):
    if matrix is None:
        matrix = np.array([[900.0, 0, 640.0], [0, 920.0, 360.0], [0, 0, 1.0]])
    if distortion is None:
        distortion = np.array([-0.12, 0.015, 0.0, 0.0, 0.0])
    matrix = np.array(matrix, dtype=np.float64)
    distortion = np.array(distortion, dtype=np.float64)
    size = (1280, 720)
    eye = np.array([0.4, -1.3, 0.45])
    target = np.array([0.45, 0.4, 0.35])
    forward = target - eye
    forward = forward / np.linalg.norm(forward)
    up = np.array([0.0, 0.0, 1.0])
    right = np.cross(forward, up)
    right = right / np.linalg.norm(right)
    down = np.cross(forward, right)
    rotation = np.stack([right, down, forward])
    rvec = cv2.Rodrigues(rotation)[0]
    tvec = -rotation @ eye
    centers = {
        40: np.array([0.0, 0.0, 0.05]),
        41: np.array([0.9, 0.05, 0.0]),
        42: np.array([0.05, 0.55, 0.1]),
        43: np.array([0.85, 0.6, 0.15]),
        44: np.array([0.15, 0.25, 0.7]),
        45: np.array([0.75, 0.35, 0.65]),
    }
    side = 0.18
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    canvas = np.full((size[1], size[0]), 255, np.uint8)
    for marker_id, center in centers.items():
        bit = cv2.aruco.generateImageMarker(dictionary, marker_id, 240, borderBits=1)
        height, width = bit.shape[:2]

        def corner(u, v, center=center, width=width, height=height):
            return center + (u / width - 0.5) * side * right + (v / height - 0.5) * side * down

        world = np.array([corner(0, 0), corner(width, 0), corner(width, height), corner(0, height)], np.float64)
        projected, _ = cv2.projectPoints(world, rvec, tvec, matrix, np.zeros(5))
        source = np.array([[0, 0], [width, 0], [width, height], [0, height]], np.float32)
        homography = cv2.getPerspectiveTransform(source, projected.reshape(4, 2).astype(np.float32))
        warped = cv2.warpPerspective(bit, homography, size, flags=cv2.INTER_LINEAR, borderValue=255)
        mask = cv2.warpPerspective(np.full(bit.shape, 255, np.uint8), homography, size, borderValue=0)
        canvas[mask > 0] = warped[mask > 0]
    height, width = canvas.shape[:2]
    xs, ys = np.meshgrid(np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))
    points = np.stack([xs, ys], axis=-1).reshape(-1, 1, 2)
    mapped = cv2.undistortPoints(points, matrix, distortion, P=matrix).reshape(height, width, 2)
    image = cv2.remap(
        canvas,
        mapped[..., 0],
        mapped[..., 1],
        cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255,
    )
    return image, centers, matrix, distortion, np.r_[rvec.ravel(), tvec.ravel()]


def test_synthetic_markers_match_truth_and_recover_pose() -> None:
    image, centers, matrix, distortion, truth = _marker_scene()
    detections = detect_control_points(image)
    assert [item["marker_id"] for item in detections] == sorted(centers)
    for item in detections:
        projected, _ = cv2.projectPoints(
            centers[item["marker_id"]].reshape(1, 1, 3),
            truth[:3],
            truth[3:],
            matrix,
            distortion,
        )
        assert np.linalg.norm(np.array(item["pixel"]) - projected.reshape(2)) < 1.5
    worlds = {marker_id: tuple(float(axis) for axis in center) for marker_id, center in centers.items()}
    landmarks = landmarks_from_points(detections, worlds)
    for landmark in landmarks:
        assert landmark["world_m"] == list(worlds[landmark["marker_id"]])
    rms, pose = fit_extrinsics(matrix, distortion, landmarks, 2.0)
    assert rms < 1.0
    estimated = cv2.Rodrigues(pose[:3])[0]
    actual = cv2.Rodrigues(truth[:3])[0]
    angle = np.degrees(np.arccos(np.clip((np.trace(estimated @ actual.T) - 1) / 2, -1, 1)))
    assert angle < 1.0
    assert np.linalg.norm(pose[3:] - truth[3:]) < 0.02


def test_health_reports_frozen_before_blur() -> None:
    sharp = np.zeros((180, 240, 3), np.uint8)
    sharp[::8, :, :] = 255
    sharp[:, ::8, :] = 255
    status, gray = assess_frame(None, sharp)
    assert status == "ok"
    status, _same = assess_frame(gray, sharp)
    assert status == "frozen"
    blurry = np.zeros((180, 240, 3), np.uint8)
    blurry[:, :, 0] = np.linspace(0, 40, 240, dtype=np.uint8)
    moved = blurry.copy()
    moved[:, :, 0] = np.linspace(5, 45, 240, dtype=np.uint8)
    status, gray = assess_frame(None, blurry)
    assert status == "blur"
    status, _gray = assess_frame(gray, moved)
    assert status == "blur"


def test_intrinsics_only_calibration_is_not_localized(tmp_path: Path) -> None:
    config = load_config(EXAMPLE)
    now = datetime(2026, 11, 14, tzinfo=UTC)
    frame = FrameShot(camera_id=1, jpeg=b"\xff\xd8\xff", captured_at=now, width=32, height=24)
    calibration = {
        "intrinsics": [[800, 0, 16], [0, 800, 12], [0, 0, 1]],
        "distortion": [0, 0, 0, 0, 0],
        "landmarks": [],
    }
    position = locate_position(config, [frame], {1: calibration}, [])
    assert position == {"status": "UNOBSERVABLE", "support_camera_ids": []}
    full = {
        **calibration,
        "landmarks": [
            {"world_m": [0, 0, 0], "pixel": [1, 1], "marker_id": 40},
            {"world_m": [1, 0, 0], "pixel": [10, 1], "marker_id": 41},
            {"world_m": [1, 1, 0], "pixel": [10, 10], "marker_id": 42},
            {"world_m": [0, 1, 0], "pixel": [1, 10], "marker_id": 43},
        ],
    }
    manifest = write_manifest(tmp_path, 2.0, [frame], {1: full}, [])
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["views"]["1"]["landmarks"][0] == {"world_m": [0, 0, 0], "pixel": [1, 1]}


def test_api_saves_intrinsics_then_extrinsics(tmp_path: Path) -> None:
    client = _client(tmp_path)
    admin = _auth(client)
    created = client.post(
        "/api/v1/cameras",
        headers=admin,
        json={
            "name": "摄像头1",
            "source_type": "USB",
            "source_uri": "MF-200",
            "stream_key": "cam1",
            "target_fps": 15,
        },
    )
    assert created.status_code == 200
    camera_id = created.json()["id"]
    images, _matrix, _distortion = _render_charuco_views()
    saved = client.post(
        f"/api/v1/cameras/{camera_id}/calibration/intrinsics",
        headers=admin,
        data={"paper": "a4"},
        files=[("files", (f"{index}.png", _png(image), "image/png")) for index, image in enumerate(images)],
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()["calibration"]
    assert body["intrinsics_reprojection_error_px"] < 0.5
    assert body["landmarks"] == []
    assert body["board"] == "a4"
    room = client.post("/api/v1/rooms", headers=admin, json={"name": "101", "scene_type": "classroom"})
    listed = client.put(
        f"/api/v1/rooms/{room.json()['id']}/cameras",
        headers=admin,
        json={"camera_ids": [camera_id, None, None, None]},
    )
    assert listed.json()["cameras"][0]["calibrated"] is False

    stored_matrix = body["intrinsics"]
    stored_distortion = body["distortion"]
    scene, centers, _matrix, _distortion, _truth = _marker_scene(stored_matrix, stored_distortion)
    detected = client.post(
        f"/api/v1/cameras/{camera_id}/calibration/detect",
        headers=admin,
        files={"file": ("scene.png", _png(scene), "image/png")},
    )
    assert detected.status_code == 200, detected.text
    points = [
        {"marker_id": item["marker_id"], "world_m": [float(axis) for axis in centers[item["marker_id"]]]}
        for item in detected.json()["markers"]
    ]
    extrinsic = client.post(
        f"/api/v1/cameras/{camera_id}/calibration/extrinsics",
        headers=admin,
        data={"points": json.dumps(points)},
        files={"file": ("scene.png", _png(scene), "image/png")},
    )
    assert extrinsic.status_code == 200, extrinsic.text
    stored = extrinsic.json()["calibration"]
    assert stored["extrinsics_reprojection_error_px"] < 2
    assert len(stored["landmarks"]) == len(centers)
    for landmark in stored["landmarks"]:
        assert landmark["world_m"] == [float(axis) for axis in centers[landmark["marker_id"]]]
    listed = client.get("/api/v1/rooms", headers=admin)
    assert listed.json()[0]["cameras"][0]["calibrated"] is True
    sheets = client.get("/api/v1/calibration/boards/charuco?paper=a4", headers=admin)
    assert sheets.status_code == 200
    assert sheets.headers["content-type"] == "application/pdf"
    unknown = client.get("/api/v1/calibration/boards/charuco?paper=a2", headers=admin)
    assert unknown.status_code == 400


class _SharpGate:
    def __init__(self, frames) -> None:
        self.frames = frames
        self.go = threading.Event()

    def open(self, _assignment):
        return _Reader(self)


class _Reader:
    def __init__(self, gate: _SharpGate) -> None:
        self.gate = gate
        self.index = 0
        self.released = False

    def read(self):
        if self.released:
            return False, None
        if not self.gate.go.wait(0.05):
            return False, None
        frame = self.gate.frames[self.index % len(self.gate.frames)]
        self.index += 1
        return True, frame

    def release(self) -> None:
        self.released = True


class _QuietDetector:
    model_version = "test"

    def detect(self, images):
        return [[] for _image in images]


def test_live_health_frozen_and_blur(tmp_path: Path) -> None:
    config = load_config(EXAMPLE)
    engine = make_engine(f"sqlite:///{tmp_path / 'health.db'}")
    from fire_monitoring.db import Base, make_session_factory

    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    session = factory()
    now = datetime.now(UTC)
    session.add(Room(name="101", scene_type="classroom", created_at=now))
    session.commit()
    room = session.query(Room).one()
    sharp = np.zeros((96, 128, 3), np.uint8)
    sharp[::4, :, :] = 255
    sharp[:, ::4, :] = 255
    session.add(
        Camera(
            name="摄像头",
            source_type="USB",
            source_uri="cam",
            stream_key="cam",
            target_fps=20,
            calibration_json=None,
            created_at=now,
        )
    )
    session.commit()
    camera = session.query(Camera).one()
    session.add(RoomCamera(room_id=room.id, camera_id=camera.id, slot=1))
    session.commit()
    room_id = room.id
    camera_id = camera.id
    session.close()
    gate = _SharpGate([sharp])
    gate.go.set()
    app = create_app(
        config,
        engine=engine,
        evidence=MemoryStore(),
        detector=_QuietDetector(),
        open_capture=gate.open,
        on_fatal=lambda: None,
        start_worker=True,
    )
    with TestClient(app) as client:
        token = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "123456"}
        ).json()["access_token"]
        deadline = time.monotonic() + 5
        health = None
        while time.monotonic() < deadline:
            response = client.get(f"/api/v1/rooms/{room_id}/live", headers={"Authorization": f"Bearer {token}"})
            assert response.status_code == 200
            health = response.json()["cameras"][0]["health"]
            if health == "frozen":
                break
            time.sleep(0.05)
        assert health == "frozen"
        png = client.get(f"/api/v1/cameras/{camera_id}/frame", headers={"Authorization": f"Bearer {token}"})
        assert png.status_code == 200
        assert png.headers["content-type"] == "image/png"
