from __future__ import annotations

import json

from sqlalchemy import select

from ..config import AppConfig, load_config
from ..db import make_engine, make_session_factory, mysql_url
from ..models import Camera


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_mediamtx(config: AppConfig, cameras: list[Camera]) -> str:
    media = config.mediamtx
    lines = [
        "logLevel: info",
        "logDestinations: [stdout]",
        "api: yes",
        f"apiAddress: {media.api_address}",
        "playback: yes",
        f"playbackAddress: {media.playback_address}",
        "rtsp: yes",
        f"rtspAddress: {media.rtsp_address}",
        "rtspTransports: [tcp]",
        "hls: yes",
        f"hlsAddress: {media.hls_address}",
        "webrtc: yes",
        f"webrtcAddress: {media.webrtc_address}",
        f"webrtcLocalUDPAddress: {media.webrtc_udp_address}",
        "webrtcAdditionalHosts: [127.0.0.1, localhost]",
        "authInternalUsers:",
        "  - user: any",
        "    pass:",
        "    ips: []",
        "    permissions:",
        "      - action: publish",
        "        path:",
        "      - action: read",
        "        path:",
        "      - action: playback",
        "        path:",
        "      - action: api",
        "pathDefaults:",
        "  source: publisher",
        "  overridePublisher: yes",
        "  record: yes",
        "  recordPath: runtime/recordings/%path/%Y-%m-%d_%H-%M-%S-%f",
        "  recordFormat: fmp4",
        "  recordDeleteAfter: 10m",
        "paths:",
    ]
    for camera in cameras:
        lines.append(f"  {camera.stream_key}:")
        if camera.source_type == "RTSP":
            lines.append(f"    source: {_quote(camera.source_uri)}")
            lines.append("    rtspTransport: tcp")
        else:
            lines.append("    source: publisher")
    lines.append("  all_others:")
    lines.append("    source: publisher")
    return "\n".join(lines) + "\n"


def main() -> None:
    from pathlib import Path

    config = load_config()
    engine = make_engine(mysql_url(config))
    factory = make_session_factory(engine)
    session = factory()
    cameras = list(session.scalars(select(Camera).order_by(Camera.id)))
    session.close()
    text = render_mediamtx(config, cameras)
    path = Path(config.mediamtx.config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    usb = [
        {
            "stream_key": camera.stream_key,
            "device": camera.source_uri,
            "fps": max(1, int(round(camera.target_fps))),
            "url": f"{config.mediamtx.rtsp_base.rstrip('/')}/{camera.stream_key}",
        }
        for camera in cameras
        if camera.source_type == "USB"
    ]
    print(json.dumps({"config_path": str(path), "usb": usb}, ensure_ascii=False), flush=True)
