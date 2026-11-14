from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

from ..localization.observe import locate_position
from .service import actuate, notify_room, record_alert, write_analysis, write_position

logger = logging.getLogger("fire_monitoring.alerts")


@dataclass
class ConfirmedJob:
    room_id: int
    alert_type: str
    started_at: datetime
    sources: list
    calibrations: dict
    frames: list
    pump_observations: list[dict]
    confirmed_monotonic: float
    alert_id: int | None = None
    room_name: str = ""
    analysis: dict | None = None
    analysis_ready: threading.Event = field(default_factory=threading.Event)


class AlertPipeline:
    def __init__(
        self,
        config,
        session_factory,
        evidence,
        analyzer,
        sms,
        pump,
        events,
        *,
        localizer=None,
        on_fatal=None,
    ) -> None:
        self.config = config
        self.session_factory = session_factory
        self.evidence = evidence
        self.analyzer = analyzer
        self.sms = sms
        self.pump = pump
        self.events = events
        self.localizer = localizer
        self.on_fatal = on_fatal or _exit_process
        self.failed = False
        self._inbox: queue.Queue = queue.Queue(maxsize=32)
        self._localize: queue.Queue = queue.Queue()
        self._qwen: queue.Queue = queue.Queue()
        self._sms: queue.Queue = queue.Queue()
        self._pump: queue.Queue = queue.Queue()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        specs = [
            ("alert-coordinator", self._inbox, self._coordinate),
            ("alert-localize", self._localize, self._localize_job),
            ("alert-qwen", self._qwen, self._analyze_job),
            ("alert-sms", self._sms, self._sms_job),
            ("alert-pump", self._pump, self._pump_job),
        ]
        for name, work, handler in specs:
            thread = threading.Thread(
                target=self._run,
                args=(work, handler),
                name=name,
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)

    def submit(self, job: ConfirmedJob) -> None:
        self._inbox.put_nowait(job)

    def wait(self, timeout: float = 5) -> None:
        deadline = time.monotonic() + timeout
        queues = [self._inbox, self._localize, self._qwen, self._sms, self._pump]
        while time.monotonic() < deadline:
            if all(item.unfinished_tasks == 0 for item in queues):
                return
            time.sleep(0.01)
        raise TimeoutError("alert pipeline did not finish")

    def stop(self) -> None:
        self._inbox.put(None)
        for work in (self._localize, self._qwen, self._sms, self._pump):
            work.put(None)
        for thread in self._threads:
            thread.join(timeout=5)
            if thread.is_alive():
                raise RuntimeError(f"{thread.name} did not stop")

    def _run(self, work: queue.Queue, handler) -> None:
        while True:
            job = work.get()
            try:
                if job is None:
                    return
                handler(job)
            except Exception:
                logger.exception("%s failed", threading.current_thread().name)
                self.failed = True
                self.on_fatal()
                return
            finally:
                work.task_done()

    def _coordinate(self, job: ConfirmedJob) -> None:
        session = self.session_factory()
        try:
            alert, payload = record_alert(
                session,
                room_id=job.room_id,
                alert_type=job.alert_type,
                started_at=job.started_at,
                sources=job.sources,
                frames=job.frames,
                evidence=self.evidence,
            )
        finally:
            session.close()
        job.alert_id = alert.id
        job.room_name = payload["room_name"]
        self.events.publish(payload)
        latency_ms = (time.perf_counter() - job.confirmed_monotonic) * 1000
        logger.info("alert %s popup %.1f ms after confirmation", alert.id, latency_ms)
        self._localize.put(job)
        self._qwen.put(job)
        self._sms.put(job)
        self._pump.put(job)

    def _localize_job(self, job: ConfirmedJob) -> None:
        position = locate_position(
            self.config,
            job.frames,
            job.calibrations,
            job.sources,
            localizer=self.localizer,
        )
        session = self.session_factory()
        try:
            payload = write_position(session, job.alert_id, position)
        finally:
            session.close()
        self.events.publish(payload)

    def _analyze_job(self, job: ConfirmedJob) -> None:
        try:
            jpegs = [frame.jpeg for frame in job.frames]
            if self.config.llm.enabled and self.analyzer is not None and jpegs:
                job.analysis = self.analyzer.analyze(job.alert_id, jpegs)
                session = self.session_factory()
                try:
                    payload = write_analysis(session, job.alert_id, job.analysis)
                finally:
                    session.close()
                self.events.publish(payload)
        finally:
            job.analysis_ready.set()

    def _sms_job(self, job: ConfirmedJob) -> None:
        session = self.session_factory()
        try:
            payload = notify_room(
                session,
                self.sms,
                alert_id=job.alert_id,
                room_id=job.room_id,
                room_name=job.room_name,
                alert_type=job.alert_type,
                when=job.started_at,
            )
        finally:
            session.close()
        if payload is not None:
            self.events.publish(payload)

    def _pump_job(self, job: ConfirmedJob) -> None:
        analysis = None
        if self.config.pump.require_vlm:
            if not job.analysis_ready.wait(30):
                raise TimeoutError("qwen did not finish within 30s")
            analysis = job.analysis
        session = self.session_factory()
        try:
            payload = actuate(
                session,
                self.pump,
                alert_id=job.alert_id,
                room_id=job.room_id,
                alert_type=job.alert_type,
                observations=job.pump_observations,
                analysis=analysis,
                captured_at=job.started_at,
                model_version=self.config.model.version,
            )
        finally:
            session.close()
        if payload is not None:
            self.events.publish(payload)


def _exit_process() -> None:
    import os

    os._exit(1)
