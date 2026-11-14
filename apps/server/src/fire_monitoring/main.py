from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .alerts.router import router as alerts_router
from .analysis.qwen import QwenAnalyzer
from .auth.router import router as auth_router
from .auth.security import seed_users
from .cameras.router import router as cameras_router
from .config import AppConfig
from .config.router import router as config_router
from .db import make_engine, make_session_factory, mysql_url
from .detection.router import router as detection_router
from .detection.worker import DetectionWorker, LiveHub
from .events.hub import EventHub
from .events.router import router as events_router
from .evidence.store import MinioStore
from .pump.bridge import build_pump
from .pump.router import router as pump_router
from .rooms.router import router as rooms_router
from .sms.aliyun import AliyunSmsSender
from .sms.service import SmsService


def create_app(
    config: AppConfig,
    *,
    engine=None,
    evidence=None,
    analyzer=None,
    sms_sender=None,
    pump=None,
    start_worker: bool = True,
    detector=None,
    open_capture=None,
    localizer=None,
    on_fatal=None,
) -> FastAPI:
    from . import models

    engine = engine or make_engine(mysql_url(config))
    models.Base.metadata.create_all(engine)
    session_factory = make_session_factory(engine)
    session = session_factory()
    seed_users(session, config)
    session.close()

    evidence = evidence if evidence is not None else MinioStore(config)
    if analyzer is None and config.llm.enabled:
        analyzer = QwenAnalyzer(config)
    sms = SmsService(config, sms_sender or AliyunSmsSender(config.sms))
    pump_started = False
    if pump is None and config.pump.enabled:
        pump = build_pump(config)
        pump.start()
        pump_started = True
    live = LiveHub()
    events = EventHub()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.events.bind(asyncio.get_running_loop())
        yield
        if app.state.worker is not None:
            app.state.worker.stop()
        if app.state.pump is not None and app.state.pump_started:
            app.state.pump.close()

    app = FastAPI(title="火情监控", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.server.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(rooms_router, prefix="/api/v1")
    app.include_router(cameras_router, prefix="/api/v1")
    app.include_router(detection_router, prefix="/api/v1")
    app.include_router(alerts_router, prefix="/api/v1")
    app.include_router(config_router, prefix="/api/v1")
    app.include_router(pump_router, prefix="/api/v1")
    app.include_router(events_router, prefix="/api/v1")
    app.state.config = config
    app.state.session_factory = session_factory
    app.state.evidence = evidence
    app.state.analyzer = analyzer
    app.state.sms = sms
    app.state.pump = pump
    app.state.pump_started = pump_started
    app.state.live = live
    app.state.events = events
    app.state.worker = None
    if start_worker:
        worker = DetectionWorker(
            config,
            session_factory,
            evidence,
            analyzer,
            sms,
            pump,
            live,
            events,
            detector=detector,
            open_capture=open_capture,
            localizer=localizer,
            on_fatal=on_fatal,
        )
        app.state.worker = worker
        worker.start()
    return app
