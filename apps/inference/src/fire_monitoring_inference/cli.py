from __future__ import annotations

import argparse
import copy
import json
import logging
import sys
import threading
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from .api import create_app
from .camera_control import CameraControl, CameraStart
from .config import ServiceConfig
from .contracts import EventEnvelope
from .detectors.mock import MockDetector
from .fusion import DualCameraFusion, FusionConfig
from .live import CameraError, LiveCameraConfig, LiveCameraRunner, OpenCVCameraSource
from .live_frames import LiveFrameBuffer
from .pipeline import InferencePipeline
from .publisher import (
    EventPublisher,
    MemoryEventPublisher,
    RedisStreamPublisher,
    StdoutEventPublisher,
)
from .replay import MockReplayRunner, built_in_demo_frames, load_jsonl, write_example
from .runtime import RuntimeState
from .temporal import TemporalConfig


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fire-inference")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="start the Flask management API")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    serve.add_argument("--redis", action="store_true", help="require Redis readiness")
    serve.add_argument("--replay", type=Path, help="run a JSONL replay in a worker thread")
    serve.add_argument("--pace", type=float, default=0)
    serve.add_argument("--camera-model", type=Path, help="run one local camera with this model")
    serve.add_argument("--camera-autostart", action=argparse.BooleanOptionalAction, default=True)
    serve.add_argument("--camera-index", type=int, default=0)
    serve.add_argument("--device", default="0")
    serve.add_argument("--imgsz", type=int, default=640)
    serve.add_argument("--confidence", type=float, default=0.25)
    serve.add_argument("--target-fps", type=float, default=5.0)
    serve.add_argument("--site-id", type=int, default=1)
    serve.add_argument("--zone-id", type=int, default=1)
    serve.add_argument("--camera-id", type=int, default=1)
    serve.add_argument(
        "--enrich",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="store confirmed evidence and run configured cloud semantics",
    )

    replay = subparsers.add_parser("replay", help="emit deterministic mock inference events")
    replay.add_argument("--input", type=Path, help="JSONL input; omit for the built-in demo")
    replay.add_argument("--publisher", choices=("stdout", "redis", "memory"), default="stdout")
    replay.add_argument("--pace", type=float, default=0, help="0=fast; 1=recorded timing")

    camera = subparsers.add_parser(
        "camera", help="run YOLO on one local camera through the temporal event pipeline"
    )
    camera.add_argument("--model", type=Path, required=True, help="path to a YOLO .pt model")
    camera.add_argument("--model-version", default="yolo11s-fire-smoke-primary-v2")
    camera.add_argument("--camera-index", type=int, default=0)
    camera.add_argument("--device", default="0", help="Ultralytics device, normally 0 or cpu")
    camera.add_argument("--imgsz", type=int, default=640)
    camera.add_argument("--confidence", type=float, default=0.25)
    camera.add_argument("--half", action=argparse.BooleanOptionalAction, default=True)
    camera.add_argument("--width", type=int, default=1280)
    camera.add_argument("--height", type=int, default=720)
    camera.add_argument("--target-fps", type=float, default=5.0)
    camera.add_argument("--max-frames", type=int, default=0, help="0 runs until Q/Esc/Ctrl+C")
    camera.add_argument("--site-id", type=int, default=1)
    camera.add_argument("--zone-id", type=int, default=1)
    camera.add_argument("--camera-id", type=int, default=1)
    camera.add_argument("--publisher", choices=("memory", "stdout", "redis"), default="memory")
    camera.add_argument("--preview", action=argparse.BooleanOptionalAction, default=False)

    doctor = subparsers.add_parser("doctor", help="verify CUDA and the local YOLO model")
    doctor.add_argument("--model", type=Path, required=True)
    doctor.add_argument("--device-index", type=int, default=0)

    example = subparsers.add_parser("write-example", help="write the built-in replay JSONL")
    example.add_argument("path", type=Path)

    validate = subparsers.add_parser("validate-event", help="validate an event envelope JSON file")
    validate.add_argument("path", type=Path)
    return parser


def _publisher(name: str, config: ServiceConfig) -> EventPublisher:
    if name == "redis":
        return RedisStreamPublisher(config.redis_url, stream=config.redis_stream)
    if name == "memory":
        return MemoryEventPublisher()
    return StdoutEventPublisher()


def _runner(
    config: ServiceConfig, publisher: EventPublisher, runtime: RuntimeState
) -> MockReplayRunner:
    pipeline = _pipeline(
        config,
        publisher,
        runtime,
        model_version=config.model_version,
    )
    return MockReplayRunner(detector=MockDetector(), pipeline=pipeline)


def _pipeline(
    config: ServiceConfig,
    publisher: EventPublisher,
    runtime: RuntimeState,
    *,
    model_version: str,
    defer_confirmed: bool = False,
) -> InferencePipeline:
    temporal = TemporalConfig(
        n=config.temporal_n,
        m=config.temporal_m,
        candidate_n=config.candidate_n,
        min_confidence=config.min_confidence,
        clear_frames=config.clear_frames,
        cooldown_ms=config.cooldown_ms,
    )
    return InferencePipeline(
        publisher=publisher,
        source=config.source,
        model_version=model_version,
        temporal_config=temporal,
        fusion=DualCameraFusion(FusionConfig(sync_window_ms=config.fusion_window_ms)),
        runtime=runtime,
        defer_confirmed=defer_confirmed,
    )


def _serve_camera(
    *,
    args: argparse.Namespace,
    config: ServiceConfig,
    publisher: EventPublisher,
    runtime: RuntimeState,
    live_frames: LiveFrameBuffer,
    stop_event: threading.Event | None = None,
) -> None:
    enrichment = None
    source = None
    try:
        from .detectors.ultralytics_adapter import UltralyticsDetector
        from .enrichment import IncidentEnrichmentWorker
        from .evidence import MinioEvidenceStore
        from .vision.qwen import QwenVisionReasoner

        detector = UltralyticsDetector(
            str(args.camera_model),
            model_version=config.model_version,
            imgsz=args.imgsz,
            confidence=args.confidence,
            device=args.device,
            half=args.device.lower() != "cpu",
        )
        source = OpenCVCameraSource(
            camera_index=args.camera_index,
            camera_id=args.camera_id,
            requested_fps=args.target_fps,
        )
        if config.vlm_gate_enabled and not args.enrich:
            raise RuntimeError("VLM gate requires --enrich")
        if config.vlm_gate_enabled and config.dashscope_api_key is None:
            raise RuntimeError("VLM gate requires DASHSCOPE_API_KEY")
        if args.enrich:
            if config.minio_access_key is None or config.minio_secret_key is None:
                raise RuntimeError("MinIO credentials are required for incident enrichment")
            evidence_store = MinioEvidenceStore(
                endpoint=config.minio_endpoint,
                access_key=config.minio_access_key.get_secret_value(),
                secret_key=config.minio_secret_key.get_secret_value(),
                bucket=config.minio_bucket,
                secure=config.minio_secure,
            )
            reasoner = QwenVisionReasoner(
                api_key=(
                    config.dashscope_api_key.get_secret_value()
                    if config.dashscope_api_key is not None
                    else None
                ),
                base_url=config.dashscope_base_url,
                model=config.dashscope_model,
            )
            enrichment = IncidentEnrichmentWorker(
                publisher=publisher,
                evidence_store=evidence_store,
                reasoner=reasoner,
                cv2_module=source.cv2_module,
                gate_confirmed=config.vlm_gate_enabled,
                gate_min_confidence=config.vlm_gate_min_confidence,
                gate_fail_open=config.vlm_gate_fail_open,
                runtime=runtime,
            )
            enrichment.start()
        logging.getLogger(__name__).info(
            "live camera ready: index=%s backend=%s device=%s",
            args.camera_index,
            source.backend_name,
            args.device,
        )
        LiveCameraRunner(
            source=source,
            detector=detector,
            pipeline=_pipeline(
                config,
                publisher,
                runtime,
                model_version=config.model_version,
                defer_confirmed=config.vlm_gate_enabled,
            ),
            config=LiveCameraConfig(
                site_id=args.site_id,
                zone_id=args.zone_id,
                camera_id=args.camera_id,
                target_fps=args.target_fps,
            ),
            cv2_module=source.cv2_module,
            frame_buffer=live_frames,
            enrichment=enrichment,
            stop_event=stop_event,
        ).run()
    except Exception:
        runtime.fail("LIVE_CAMERA_START_FAILED")
        logging.getLogger(__name__).exception("live camera worker stopped")
    finally:
        if source is not None:
            source.release()
        if enrichment is not None:
            enrichment.stop()


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = _parser().parse_args(argv)
    config = ServiceConfig.from_env()

    if args.command == "validate-event":
        try:
            event = EventEnvelope.model_validate_json(args.path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as exc:
            print(f"invalid: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(event.to_wire(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "write-example":
        args.path.parent.mkdir(parents=True, exist_ok=True)
        write_example(args.path)
        print(args.path)
        return 0

    if args.command == "doctor":
        from .diagnostics import local_yolo_diagnostics

        try:
            result = local_yolo_diagnostics(args.model, device_index=args.device_index)
        except RuntimeError as exc:
            print(f"diagnostics failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "replay":
        publisher = _publisher(args.publisher, config)
        runtime = RuntimeState(model_version=config.model_version)
        frames = load_jsonl(args.input) if args.input else built_in_demo_frames()
        events = _runner(config, publisher, runtime).run(frames, pace=args.pace)
        if args.publisher != "stdout":
            confirmed = sum(event.event_type == "INCIDENT_CONFIRMED" for event in events)
            print(json.dumps({"events": len(events), "confirmedIncidents": confirmed}))
        return 0

    if args.command == "camera":
        if not args.model.is_file():
            print(f"model file does not exist: {args.model}", file=sys.stderr)
            return 2
        if args.device.lower() == "cpu" and args.half:
            print("FP16 is disabled automatically for CPU inference.", file=sys.stderr)
        publisher = _publisher(args.publisher, config)
        if not publisher.health():
            print("selected event publisher is not ready", file=sys.stderr)
            return 1
        runtime = RuntimeState(model_version=args.model_version)
        try:
            if not 0 <= args.confidence <= 1:
                raise ValueError("confidence must be between 0 and 1")
            if min(args.imgsz, args.width, args.height) < 1:
                raise ValueError("imgsz, width, and height must be positive")
            live_config = LiveCameraConfig(
                site_id=args.site_id,
                zone_id=args.zone_id,
                camera_id=args.camera_id,
                target_fps=args.target_fps,
                max_frames=args.max_frames,
                preview=args.preview,
            )
            from .detectors.ultralytics_adapter import UltralyticsDetector

            detector = UltralyticsDetector(
                str(args.model),
                model_version=args.model_version,
                imgsz=args.imgsz,
                confidence=args.confidence,
                device=args.device,
                half=args.half and args.device.lower() != "cpu",
            )
            pipeline = _pipeline(
                config,
                publisher,
                runtime,
                model_version=args.model_version,
            )
            source = OpenCVCameraSource(
                camera_index=args.camera_index,
                camera_id=args.camera_id,
                width=args.width,
                height=args.height,
                requested_fps=args.target_fps,
            )
            print(
                f"camera={args.camera_index} backend={source.backend_name} "
                f"model={args.model.name} device={args.device}",
                file=sys.stderr,
            )
            runner = LiveCameraRunner(
                source=source,
                detector=detector,
                pipeline=pipeline,
                config=live_config,
                cv2_module=source.cv2_module if args.preview else None,
            )
            summary = runner.run()
        except (CameraError, RuntimeError, ValueError) as exc:
            print(f"camera inference failed: {exc}", file=sys.stderr)
            return 1
        stream = sys.stderr if args.publisher == "stdout" else sys.stdout
        print(json.dumps(summary.to_dict(), ensure_ascii=False), file=stream)
        return 0

    if args.command == "serve":
        publisher = _publisher("redis" if args.redis else "memory", config)
        runtime = RuntimeState(model_version=config.model_version)
        live_frames = None
        control = None
        if args.replay and args.camera_model:
            print("replay and camera control cannot run together", file=sys.stderr)
            return 2
        if args.replay:
            frames = load_jsonl(args.replay)
            worker = threading.Thread(
                target=_runner(config, publisher, runtime).run,
                kwargs={"frames": frames, "pace": args.pace},
                name="mock-replay-worker",
                daemon=True,
            )
            worker.start()
        if args.camera_model:
            if not args.camera_model.is_file():
                print(f"model file does not exist: {args.camera_model}", file=sys.stderr)
                return 2
            try:
                import cv2

            except ImportError as exc:
                print(f"live camera dependencies are unavailable: {exc}", file=sys.stderr)
                return 1
            live_frames = LiveFrameBuffer(cv2)

            def run_camera(request: CameraStart, stop: threading.Event) -> None:
                camera_args = copy.copy(args)
                camera_args.camera_id = request.cameraId
                camera_args.zone_id = request.zoneId
                camera_args.camera_index = request.cameraIndex
                camera_args.target_fps = request.targetFps
                _serve_camera(
                    args=camera_args, config=config, publisher=publisher,
                    runtime=runtime, live_frames=live_frames, stop_event=stop,
                )

            control = CameraControl(worker=run_camera, runtime=runtime, frames=live_frames)
            if args.camera_autostart:
                control.start(CameraStart(
                    cameraId=args.camera_id, zoneId=args.zone_id,
                    cameraIndex=args.camera_index, targetFps=args.target_fps,
                ))
        app = create_app(
            config=config,
            runtime=runtime,
            publisher=publisher,
            live_frames=live_frames,
            camera_control=control,
        )
        app.run(
            host=args.host or config.host,
            port=args.port or config.port,
            threaded=True,
            use_reloader=False,
        )
        return 0
    return 2
