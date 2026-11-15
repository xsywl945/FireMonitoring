from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta

import cv2
import numpy as np
from fire_monitoring_inference.temporal import TemporalState

from ..alerts.pipeline import ConfirmedJob
from ..detection.ingest import AlertDraft, DetectionHit, DetectionState, consume_frame
from ..localization.observe import latest_in_window
from .cache import CachedAnalyzer
from .geometry import GROW_S, PENDING_S
from .pack import load_json


class DemoClock:
    def __init__(self, epoch: datetime) -> None:
        self.epoch = epoch
        self.seconds = 0.0

    def set(self, seconds: float) -> None:
        self.seconds = float(seconds)

    def monotonic(self) -> float:
        return self.seconds

    def now(self) -> datetime:
        return self.epoch + timedelta(seconds=self.seconds)


class DemoPlayer:
    def __init__(self, service) -> None:
        self.service = service
        self.clock = DemoClock(datetime.fromisoformat(service.pack["epoch"]))
        self.state = DetectionState()
        self.jpegs: dict[int, bytes] = {}
        self.running = False
        self.finished = False
        self.error: Exception | None = None
        self.script_id: str | None = None
        self.elapsed_s = 0.0
        self._persons: list[list[float]] = []
        self._escalated = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self, script_id: str, speed: float) -> None:
        if speed < 0:
            raise RuntimeError("播放速度不能为负")
        pack = self.service.pack
        if script_id not in pack["scripts"]:
            raise RuntimeError(f"没有剧本 {script_id}")
        settings = self.service.config.suppression
        if settings.pending_seconds != PENDING_S or self.service.pump.config.duration_ms != 5000:
            raise RuntimeError("示例录像按 3 秒待喷、5 秒喷射生成，和当前灭火配置不一致")
        if settings.clear_seconds != 3:
            raise RuntimeError("示例录像按 3 秒复核生成，和当前灭火配置不一致")
        with self._lock:
            if self.running:
                raise RuntimeError("演示正在播放")
            self._stop.clear()
            self.running = True
            self.finished = False
            self.error = None
            self.script_id = script_id
            self._thread = threading.Thread(
                target=self._guard,
                args=(script_id, speed),
                name="demo-player",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=30)
            if thread.is_alive():
                raise RuntimeError("演示线程没有停下来")

    def join(self, timeout: float) -> None:
        thread = self._thread
        if thread is None:
            return
        thread.join(timeout)
        if thread.is_alive():
            raise RuntimeError("演示没有在时限内结束")
        if self.error is not None:
            raise self.error

    def _guard(self, script_id: str, speed: float) -> None:
        try:
            self._play(script_id, speed)
            self.finished = True
        except Exception as exc:
            self.error = exc
            self.finished = True
        finally:
            self.running = False

    def _play(self, script_id: str, speed: float) -> None:
        service = self.service
        service.prepare_script(script_id)
        script = service.pack["scripts"][script_id]
        detections = load_json(service.pack, script["detections"])
        analyzer = CachedAnalyzer(load_json(service.pack, script["qwen"]), service.config.llm.model)
        service.pipeline.analyzer = analyzer
        clips = _clips(service.pack, script)
        count = len(detections["frames"])
        if any(len(frames) != count for frames in clips.values()):
            raise RuntimeError("录像帧数和检测框不一致")
        fps = service.pack["fps"]
        self.state = DetectionState()
        self._escalated = False
        self._persons = []
        for index in range(count):
            if self._stop.is_set():
                return
            moment = index / fps
            self.clock.set(moment)
            self.elapsed_s = moment
            self._persons = detections["frames"][index]["persons"]
            for camera in service.cameras:
                shift = int(round(camera["time_offset_ms"] / 1000 * fps))
                local = min(count - 1, index + shift)
                jpeg = clips[camera["key"]][local]
                boxes = detections["frames"][local]["cameras"][camera["key"]]
                self._consume(camera, jpeg, boxes)
            self._escalate()
            self._follow()
            if speed > 0:
                time.sleep((1 / fps) / speed)
        self.elapsed_s = count / fps

    def _consume(self, camera: dict, jpeg: bytes, boxes: list[dict]) -> None:
        service = self.service
        hits = [
            DetectionHit(item["class_name"], float(item["confidence"]), tuple(item["bbox"]))
            for item in boxes
            if item["class_name"] in {"fire", "smoke"}
        ]
        snapshot = consume_frame(
            room_id=service.room_id,
            camera_id=camera["id"],
            bound_camera_ids=[item["id"] for item in service.cameras],
            detections=hits,
            jpeg=jpeg,
            width=service.pack["width"],
            height=service.pack["height"],
            timestamp=self.clock.now(),
            state=self.state,
            config=service.config,
            on_alert=self._on_alert,
        )
        snapshot["health"] = "replay"
        snapshot["detections"].extend(
            {
                "class_name": item["class_name"],
                "confidence": item["confidence"],
                "bbox": item["bbox"],
            }
            for item in boxes
            if item["class_name"] == "person"
        )
        service.live.update(camera["id"], snapshot)
        with self._lock:
            self.jpegs[camera["id"]] = jpeg

    def _on_alert(self, draft: AlertDraft) -> None:
        self._submit(draft)

    def _escalate(self) -> None:
        if self._escalated:
            return
        service = self.service
        machine = service.suppression.machines.get(service.room_id)
        if machine is None or machine.phase != "疑似":
            return
        samples = self.state.samples.get(service.room_id, [])
        if len(samples) < 2:
            return
        span = (max(item.captured_at for item in samples) - min(item.captured_at for item in samples)).total_seconds()
        if span < GROW_S:
            return
        confirmed = [
            camera["id"]
            for camera in service.cameras
            if _fire_confirmed(self.state, service.room_id, camera["id"])
        ]
        if len(confirmed) < 2:
            return
        sources = latest_in_window(
            self.state.observations.get((service.room_id, "fire"), []),
            self.clock.now(),
            service.config.localization.window_ms,
        )
        if len({item.camera_id for item in sources}) < 2:
            raise RuntimeError("火点观测不足两路")
        observations = []
        for camera in service.cameras:
            evidence = self.state.latest.get((service.room_id, camera["id"], "fire"))
            if evidence is None or evidence.state not in {TemporalState.SUSPECT, TemporalState.CONFIRMED}:
                continue
            observations.append(
                {
                    "camera_id": camera["id"],
                    "class_name": "fire",
                    "score": evidence.score,
                    "effective_frames": evidence.effective_frames,
                    "duration_ms": evidence.duration_ms,
                }
            )
        if not observations:
            raise RuntimeError("没有可确认的火焰")
        frames = [self.state.frames[camera["id"]] for camera in service.cameras]
        self._escalated = True
        self._submit(
            AlertDraft(
                room_id=service.room_id,
                alert_type="FIRE",
                started_at=self.clock.now(),
                sources=sources,
                frames=frames,
                pump_observations=observations,
                before_jpeg=self.state.quiet_jpeg.get(service.room_id),
                after_jpeg=frames[-1].jpeg,
                samples=list(samples),
            )
        )

    def _submit(self, draft: AlertDraft) -> None:
        service = self.service
        job = ConfirmedJob(
            room_id=draft.room_id,
            alert_type=draft.alert_type,
            started_at=draft.started_at,
            sources=draft.sources,
            calibrations=service.calibrations,
            frames=draft.frames,
            pump_observations=draft.pump_observations,
            confirmed_monotonic=time.perf_counter(),
            before_jpeg=draft.before_jpeg,
            after_jpeg=draft.after_jpeg,
            samples=draft.samples,
        )
        service.pipeline.submit(job)
        service.pipeline.wait(30)
        if service.pipeline.failed:
            raise RuntimeError("告警管线失败") from service.pipeline.error

    def _follow(self) -> None:
        service = self.service
        if service.room_id not in service.suppression.context:
            return
        area = 0.0
        count = 0
        present = False
        for camera in service.cameras:
            frame = self.state.frames.get(camera["id"])
            if frame is None or frame.fire_box is None:
                continue
            present = True
            x1, y1, x2, y2 = frame.fire_box
            area += (x2 - x1) * (y2 - y1)
            count += 1
        service.suppression.tick(
            service.room_id,
            flame_present=present,
            flame_area=0.0 if count == 0 else area / count,
            captured_at=self.clock.now(),
        )

    def persons(self, room_id: int) -> list[np.ndarray]:
        del room_id
        return [np.array(item, dtype=float) for item in self._persons]


def _fire_confirmed(state: DetectionState, room_id: int, camera_id: int) -> bool:
    evidence = state.latest.get((room_id, camera_id, "fire"))
    return evidence is not None and evidence.state == TemporalState.CONFIRMED


def _clips(pack: dict, script: dict) -> dict[str, list[bytes]]:
    clips = {}
    for key, relative in script["videos"].items():
        capture = cv2.VideoCapture(str(pack["root"] / relative))
        frames = []
        while True:
            ok, image = capture.read()
            if not ok:
                break
            if image.shape[1] != pack["width"] or image.shape[0] != pack["height"]:
                capture.release()
                raise RuntimeError(f"{relative} 的尺寸和录像单不一致")
            encoded_ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if not encoded_ok:
                capture.release()
                raise RuntimeError("jpeg encode failed")
            frames.append(encoded.tobytes())
        capture.release()
        clips[key] = frames
    return clips

