from pydantic import SecretStr

from fire_monitoring_inference.api import create_app
from fire_monitoring_inference.config import ServiceConfig


def test_management_api_does_not_expose_cloud_secret() -> None:
    app = create_app(
        config=ServiceConfig(
            dashscope_api_key=SecretStr("do-not-leak"),
            redis_url="redis://:redis-secret@127.0.0.1:6379/0",
        )
    )
    client = app.test_client()

    assert client.get("/healthz").status_code == 200
    response = client.get("/api/v1/config")
    assert response.status_code == 200
    assert response.json["dashscope_configured"] is True
    assert "do-not-leak" not in response.get_data(as_text=True)
    assert "redis-secret" not in response.get_data(as_text=True)


def test_runtime_identifies_the_active_camera() -> None:
    from fire_monitoring_inference.runtime import RuntimeState

    runtime = RuntimeState(model_version="test-model")
    runtime.set_camera(camera_id=7, zone_id=3)
    runtime.start()
    client = create_app(runtime=runtime).test_client()
    response = client.get("/api/v1/runtime")
    assert response.json["cameraId"] == 7
    assert response.json["zoneId"] == 3
    assert response.json["status"] == "RUNNING"
