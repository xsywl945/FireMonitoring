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
