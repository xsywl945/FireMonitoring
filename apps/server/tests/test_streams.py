from fire_monitoring.config import load_config
from fire_monitoring.models import Camera
from fire_monitoring.streams.mediamtx import render_mediamtx

EXAMPLE = __import__("pathlib").Path(__file__).resolve().parents[3] / "config.example.json"


def test_render_publishes_usb_and_pulls_rtsp() -> None:
    config = load_config(EXAMPLE)
    usb = Camera(
        name="前置",
        source_type="USB",
        source_uri='Integrated Camera',
        stream_key="cam-usb",
        target_fps=15,
    )
    rtsp = Camera(
        name="网络",
        source_type="RTSP",
        source_uri="rtsp://10.0.0.8/live",
        stream_key="cam-rtsp",
        target_fps=15,
    )
    text = render_mediamtx(config, [usb, rtsp])
    assert "cam-usb:" in text
    assert "source: publisher" in text
    assert 'source: "rtsp://10.0.0.8/live"' in text
    assert "rtspTransport: tcp" in text
    assert "all_others:" in text
