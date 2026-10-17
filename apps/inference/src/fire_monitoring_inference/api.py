from __future__ import annotations

import hmac

from flask import Flask, Response, jsonify, request
from pydantic import ValidationError

from .camera_control import CameraControl, CameraStart, CameraStop, MultiCameraControl
from .config import ServiceConfig
from .live_frames import LiveFrameBuffer
from .publisher import EventPublisher
from .pump import PumpController
from .runtime import RuntimeState


def create_app(
    *,
    config: ServiceConfig | None = None,
    runtime: RuntimeState | None = None,
    publisher: EventPublisher | None = None,
    live_frames: LiveFrameBuffer | None = None,
    camera_control: CameraControl | MultiCameraControl | None = None,
    pump: PumpController | None = None,
) -> Flask:
    settings = config or ServiceConfig.from_env()
    state = runtime or RuntimeState(model_version=settings.model_version)
    app = Flask(__name__)
    app.json.sort_keys = False

    @app.before_request
    def authorize_camera_control() -> tuple[object, int] | None:
        if request.path.startswith(("/api/v1/local-cameras", "/api/v1/pump")):
            if not hmac.compare_digest(
                request.headers.get("X-Control-Token", ""),
                settings.control_token.get_secret_value(),
            ):
                return jsonify({"message": "摄像头控制需要授权"}), 403
        return None

    @app.get("/api/v1/pump")
    def pump_status() -> tuple[object, int]:
        if pump is None:
            return jsonify({"message": "水泵控制服务未启动"}), 503
        return jsonify(pump.snapshot()), 200

    @app.post("/api/v1/pump/stop")
    def stop_pump() -> tuple[object, int]:
        if pump is None:
            return jsonify({"message": "水泵控制服务未启动"}), 503
        return jsonify(pump.emergency_stop()), 200

    @app.get("/api/v1/live/cameras")
    def camera_runtimes() -> tuple[object, int]:
        if isinstance(camera_control, MultiCameraControl):
            return jsonify(camera_control.snapshots()), 200
        return jsonify([state.snapshot()]), 200

    def selected_session() -> CameraControl | None:
        camera_id = None
        if "cameraId" in request.args:
            try:
                camera_id = int(request.args["cameraId"])
                if camera_id < 1:
                    raise ValueError()
            except ValueError:
                from werkzeug.exceptions import BadRequest

                raise BadRequest("cameraId must be a positive integer") from None
        if isinstance(camera_control, MultiCameraControl):
            return camera_control.session(camera_id)
        if camera_control is not None and camera_id is not None:
            if camera_control.runtime.snapshot().get("cameraId") != camera_id:
                return None
        return camera_control

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
            data = CameraStop.model_validate(request.get_json(silent=True) or {})
            result = (camera_control.stop(data.cameraId)
                      if isinstance(camera_control, MultiCameraControl) else camera_control.stop())
            return jsonify(result), 200
        except ValidationError:
            return jsonify({"message": "摄像头参数不正确"}), 400
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
        session = selected_session()
        if session is not None:
            return jsonify(session.runtime.snapshot()), 200
        if "cameraId" in request.args:
            return jsonify(RuntimeState(model_version=settings.model_version).snapshot()), 200
        return jsonify(state.snapshot()), 200

    @app.get("/api/v1/config")
    def get_config() -> tuple[object, int]:
        return jsonify(settings.public_dict()), 200

    @app.get("/api/v1/live/status")
    def live_status() -> tuple[object, int]:
        session = selected_session()
        frames = session.frames if session is not None else (
            None if "cameraId" in request.args else live_frames)
        if frames is None:
            return jsonify({"ready": False, "detections": []}), 200
        return jsonify(frames.status()), 200

    @app.get("/api/v1/live/stream.mjpg")
    def live_stream() -> Response:
        session = selected_session()
        frames = session.frames if session is not None else (
            None if "cameraId" in request.args else live_frames)
        if frames is None:
            return Response(status=503)
        response = Response(
            frames.mjpeg(),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return response

    return app
