from __future__ import annotations

from flask import Flask, Response, jsonify

from .config import ServiceConfig
from .live_frames import LiveFrameBuffer
from .publisher import EventPublisher
from .runtime import RuntimeState


def create_app(
    *,
    config: ServiceConfig | None = None,
    runtime: RuntimeState | None = None,
    publisher: EventPublisher | None = None,
    live_frames: LiveFrameBuffer | None = None,
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

    @app.get("/api/v1/live/status")
    def live_status() -> tuple[object, int]:
        if live_frames is None:
            return jsonify({"ready": False, "detections": []}), 200
        return jsonify(live_frames.status()), 200

    @app.get("/api/v1/live/stream.mjpg")
    def live_stream() -> Response:
        if live_frames is None:
            return Response(status=503)
        response = Response(
            live_frames.mjpeg(),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return response

    return app
