import threading

from fire_monitoring_inference.api import create_app
from fire_monitoring_inference.camera_control import CameraControl
from fire_monitoring_inference.config import ServiceConfig
from fire_monitoring_inference.live_frames import LiveFrameBuffer
from fire_monitoring_inference.runtime import RuntimeState


def test_camera_control_requires_authorization_and_valid_parameters() -> None:
    runtime = RuntimeState(model_version="test")
    frames = LiveFrameBuffer(object())
    control = CameraControl(worker=lambda request, stop: None, runtime=runtime, frames=frames)
    client = create_app(camera_control=control).test_client()
    assert client.post("/api/v1/local-cameras/start", json={}).status_code == 403
    headers = {"X-Control-Token": "local-camera-control"}
    assert (
        client.post(
            "/api/v1/local-cameras/start",
            headers=headers,
            json={"cameraId": 1, "zoneId": 1, "cameraIndex": -1},
        ).status_code
        == 400
    )
    config = ServiceConfig().public_dict()
    assert "control_token" not in config


def test_stop_releases_worker_before_another_camera_can_start() -> None:
    runtime = RuntimeState(model_version="test")
    frames = LiveFrameBuffer(object())
    ready = threading.Event()
    released = threading.Event()

    def worker(request, stop):
        runtime.start()
        ready.set()
        stop.wait(5)
        released.set()
        runtime.stop()

    control = CameraControl(
        worker=worker,
        runtime=runtime,
        frames=frames,
        devices=lambda: [
            {"index": 0, "name": "Integrated Camera"},
            {"index": 1, "name": "USB Camera"},
        ],
    )
    client = create_app(runtime=runtime, live_frames=frames, camera_control=control).test_client()
    headers = {"X-Control-Token": "local-camera-control"}
    assert client.get("/api/v1/local-cameras", headers=headers).json[1]["name"] == "USB Camera"
    payload = {"cameraId": 2, "zoneId": 7, "cameraIndex": 1}
    assert (
        client.post("/api/v1/local-cameras/start", headers=headers, json=payload).status_code == 202
    )
    assert ready.wait(1)
    assert (
        client.post("/api/v1/local-cameras/start", headers=headers, json=payload).status_code == 409
    )
    assert runtime.snapshot()["cameraIndex"] == 1
    assert client.post("/api/v1/local-cameras/stop", headers=headers).status_code == 200
    assert released.is_set()
    assert frames.status()["ready"] is False
    assert runtime.snapshot()["status"] == "STOPPED"
    payload["cameraIndex"] = 0
    assert (
        client.post("/api/v1/local-cameras/start", headers=headers, json=payload).status_code == 202
    )
    assert client.post("/api/v1/local-cameras/stop", headers=headers).status_code == 200


def test_virtual_camera_filters_do_not_shift_device_indices(monkeypatch) -> None:
    import subprocess

    from fire_monitoring_inference.camera_control import local_devices

    output = "\n".join(
        [
            '[dshow] "Integrated Camera" (video)',
            '[dshow] Alternative name "physical"',
            '[dshow] "Virtual Camera" (none)',
            '[dshow] Alternative name "@device_sw_{860BB310-5D01}"',
            '[dshow] "USB Camera" (video)',
            '[dshow] "Microphone" (audio)',
        ]
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=[], returncode=1, stderr=output),
    )
    assert local_devices()[2] == {"index": 2, "name": "USB Camera"}
