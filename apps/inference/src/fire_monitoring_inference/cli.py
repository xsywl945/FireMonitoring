from __future__ import annotations

import argparse
import json
import sys
import threading
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from .api import create_app
from .config import ServiceConfig
from .contracts import EventEnvelope
from .detectors.mock import MockDetector
from .fusion import DualCameraFusion, FusionConfig
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

    replay = subparsers.add_parser("replay", help="emit deterministic mock inference events")
    replay.add_argument("--input", type=Path, help="JSONL input; omit for the built-in demo")
    replay.add_argument("--publisher", choices=("stdout", "redis", "memory"), default="stdout")
    replay.add_argument("--pace", type=float, default=0, help="0=fast; 1=recorded timing")

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
    temporal = TemporalConfig(
        n=config.temporal_n,
        m=config.temporal_m,
        candidate_n=config.candidate_n,
        min_confidence=config.min_confidence,
        clear_frames=config.clear_frames,
        cooldown_ms=config.cooldown_ms,
    )
    pipeline = InferencePipeline(
        publisher=publisher,
        source=config.source,
        model_version=config.model_version,
        temporal_config=temporal,
        fusion=DualCameraFusion(FusionConfig(sync_window_ms=config.fusion_window_ms)),
        runtime=runtime,
    )
    return MockReplayRunner(detector=MockDetector(), pipeline=pipeline)


def main(argv: Sequence[str] | None = None) -> int:
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

    if args.command == "replay":
        publisher = _publisher(args.publisher, config)
        runtime = RuntimeState(model_version=config.model_version)
        frames = load_jsonl(args.input) if args.input else built_in_demo_frames()
        events = _runner(config, publisher, runtime).run(frames, pace=args.pace)
        if args.publisher != "stdout":
            confirmed = sum(event.event_type == "INCIDENT_CONFIRMED" for event in events)
            print(json.dumps({"events": len(events), "confirmedIncidents": confirmed}))
        return 0

    if args.command == "serve":
        publisher = _publisher("redis" if args.redis else "memory", config)
        runtime = RuntimeState(model_version=config.model_version)
        if args.replay:
            frames = load_jsonl(args.replay)
            worker = threading.Thread(
                target=_runner(config, publisher, runtime).run,
                kwargs={"frames": frames, "pace": args.pace},
                name="mock-replay-worker",
                daemon=True,
            )
            worker.start()
        app = create_app(config=config, runtime=runtime, publisher=publisher)
        app.run(
            host=args.host or config.host,
            port=args.port or config.port,
            threaded=True,
            use_reloader=False,
        )
        return 0
    return 2
