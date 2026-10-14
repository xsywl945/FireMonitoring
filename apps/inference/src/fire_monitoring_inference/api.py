from __future__ import annotations

import hmac

from flask import Flask, Response, jsonify, request
from pydantic import ValidationError

from .camera_control import CameraControl, CameraStart
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
    camera_control: CameraControl | None = None,
) -> Flask:
    settings = config or ServiceConfig.from_env()
    state = runtime or RuntimeState(model_version=settings.model_version)
    app = Flask(__name__)
    app.json.sort_keys = False

    @app.before_request
    def authorize_camera_control() -> tuple[object, int] | None:
        if request.path.startswith("/api/v1/local-cameras"):
            if not hmac.compare_digest(
                request.headers.get("X-Control-Token", ""),
                settings.control_token.get_secret_value(),
            ):
                return jsonify({"message": "摄像头控制需要授权"}), 403
        return None

    @app.get("/api/v1/local-cameras")
    def cameras() -> tuple[object, int]:
        if camera_control is None:
            return jsonify({"message": "请启动摄像头控制服务"}), 503
        try:
            return jsonify(camera_control.devices()), 200
        except RuntimeError as exc:
            return jsonify({"message": str(exc)}), 503

    @app.post("/api/v1/local-cameras/start")
    def start_camera() -> tuple[object, int]:
        if camera_control is None:
            return jsonify({"message": "请使用摄像头模式启动推理服务"}), 503
        try:
            data = CameraStart.model_validate(request.get_json(silent=True))
            return jsonify(camera_control.start(data)), 202
        except ValidationError:
            return jsonify({"message": "摄像头参数不正确"}), 400
        except RuntimeError as exc:
            return jsonify({"message": str(exc)}), 409

    @app.post("/api/v1/local-cameras/stop")
    def stop_camera() -> tuple[object, int]:
        if camera_control is None:
            return jsonify({"message": "摄像头控制服务未启动"}), 503
        try:
            return jsonify(camera_control.stop()), 200
        except RuntimeError as exc:
            return jsonify({"message": str(exc)}), 409

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
