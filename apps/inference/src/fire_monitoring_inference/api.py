from __future__ import annotations

from flask import Flask, jsonify

from .config import ServiceConfig
from .publisher import EventPublisher
from .runtime import RuntimeState


def create_app(
    *,
    config: ServiceConfig | None = None,
    runtime: RuntimeState | None = None,
    publisher: EventPublisher | None = None,
) -> Flask:
    settings = config or ServiceConfig.from_env()
    state = runtime or RuntimeState(model_version=settings.model_version)
    app = Flask(__name__)
    app.json.sort_keys = False

    @app.get("/healthz")
    def health() -> tuple[object, int]:
        return jsonify(
            {
                "status": "UP",
                "service": "fire-monitoring-inference",
                "runtime": state.snapshot()["status"],
            }
        ), 200

    @app.get("/readyz")
    def readiness() -> tuple[object, int]:
        publisher_ready = publisher.health() if publisher is not None else True
        status = "UP" if publisher_ready else "DEGRADED"
        return jsonify({"status": status, "publisher": publisher_ready}), (
            200 if publisher_ready else 503
        )

    @app.get("/api/v1/runtime")
    def get_runtime() -> tuple[object, int]:
        return jsonify(state.snapshot()), 200

    @app.get("/api/v1/config")
    def get_config() -> tuple[object, int]:
        return jsonify(settings.public_dict()), 200

    return app
