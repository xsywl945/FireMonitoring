"""用演示模式和系统 Chrome 截取手册用的页面。"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import sync_playwright

from fire_monitoring.config import load_config
from fire_monitoring.db import make_engine
from fire_monitoring.evidence.store import MemoryStore
from fire_monitoring.main import create_app
from fire_monitoring.web import mount_spa

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "config.example.json"
PACK = ROOT / "data" / "demo" / "synthetic-classroom"
DIST = ROOT / "apps" / "web" / "dist"
OUT = ROOT / "docs" / "manuals" / "images"
PORT = 8099


def wait_http() -> None:
    import urllib.request

    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/openapi.json", timeout=1)
            return
        except OSError:
            time.sleep(0.2)
    raise SystemExit("演示服务没有启动")


def main() -> None:
    if not (DIST / "index.html").is_file():
        raise SystemExit("先在 apps/web 执行 npm run build")
    OUT.mkdir(parents=True, exist_ok=True)
    config = load_config(EXAMPLE)
    config.demo.enabled = True
    config.demo.pack = str(PACK)
    config.demo.hardware = "sim"
    config.demo.detector = "replay"
    config.server.host = "127.0.0.1"
    config.server.port = PORT
    work = ROOT / "runtime" / "capture"
    work.mkdir(parents=True, exist_ok=True)
    database = work / "demo.db"
    if database.exists():
        database.unlink()
    config.pump.journal_path = str(work / "pump.sqlite3")
    config.suppression.gimbal_path = str(work / "gimbal.json")
    app = create_app(
        config,
        engine=make_engine(f"sqlite:///{work / 'demo.db'}"),
        evidence=MemoryStore(),
        start_worker=False,
    )
    mount_spa(app, DIST)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    wait_http()
    base = f"http://127.0.0.1:{PORT}"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(base)
        page.get_by_text("演示模式").wait_for()
        page.locator(".login-card input").nth(0).fill("admin")
        page.locator("input[type=password]").fill("123456")
        page.screenshot(path=str(OUT / "login.png"))
        page.get_by_role("button", name="登录").click()
        page.wait_for_url("**/rooms")
        page.get_by_text("演示教室").wait_for()
        page.screenshot(path=str(OUT / "rooms.png"))
        room_id = page.evaluate(
            """async () => {
                const headers = {Authorization: 'Bearer ' + localStorage.getItem('fire_token')}
                const response = await fetch('/api/v1/rooms', {headers})
                const rooms = await response.json()
                return rooms[0].id
            }"""
        )
        page.goto(f"{base}/rooms/{room_id}")
        page.get_by_text("标定", exact=True).first.wait_for()
        page.screenshot(path=str(OUT / "calibration.png"))
        page.evaluate(
            """async () => {
                const headers = {Authorization: 'Bearer ' + localStorage.getItem('fire_token'), 'Content-Type': 'application/json'}
                const response = await fetch('/api/v1/demo/start', {method: 'POST', headers, body: JSON.stringify({script: 'full', speed: 30})})
                if (!response.ok) throw new Error(await response.text())
            }"""
        )
        page.goto(f"{base}/monitor")
        page.locator("img[alt='回放画面']").first.wait_for(timeout=30000)
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUT / "monitor.png"))
        page.goto(f"{base}/dashboard")
        page.get_by_text("校园智能火情预警").wait_for()
        page.wait_for_timeout(1000)
        page.screenshot(path=str(OUT / "dashboard.png"), full_page=True)
        page.goto(f"{base}/suppression")
        page.get_by_role("button", name="网页急停").wait_for()
        page.screenshot(path=str(OUT / "suppression.png"))
        deadline = time.time() + 90
        while time.time() < deadline:
            status = page.evaluate(
                """async () => {
                    const headers = {Authorization: 'Bearer ' + localStorage.getItem('fire_token')}
                    const response = await fetch('/api/v1/alerts', {headers})
                    if (!response.ok) return 0
                    const body = await response.json()
                    return Array.isArray(body) ? body.length : (body.items || []).length
                }"""
            )
            if status:
                break
            page.wait_for_timeout(500)
        else:
            raise SystemExit("演示剧本没有生成告警")
        page.goto(f"{base}/alerts")
        page.get_by_text("告警", exact=False).first.wait_for()
        page.screenshot(path=str(OUT / "alerts.png"))
        browser.close()
    server.should_exit = True
    for name in ("login.png", "rooms.png", "monitor.png", "dashboard.png", "suppression.png", "alerts.png", "calibration.png"):
        path = OUT / name
        if not path.is_file() or path.stat().st_size < 1000:
            raise SystemExit(f"截图无效：{path}")
    print(f"截图已写入 {OUT}")


if __name__ == "__main__":
    main()
