# Fire Monitoring

2026-11-08：YOLO26s 正式训练与微调已交付，仓库由 Codex 接管。当前状态见 [项目状态](docs/project/STATUS.md)，模型与校验值见 [训练交接](docs/training/yolo26s-handoff-2026-11-08.md)，四摄代码的实验范围见 [研究方案](docs/plans/后续四摄算法方案-YOLO26s.md)。新权重尚未接入推理服务。

最后记录的 2026-10-18 联调模式：**本地 YOLO 火焰时序识别后喷水，大模型接口暂时关闭；BOOT 按住强制喷水、松开停止（最多 30 秒）**。支持单摄/双摄，当前本机按用户要求使用一只 USB 摄像头。配置和操作以 [本地识别与 BOOT 说明](docs/runbooks/local-yolo-boot.md) 为准；下文涉及大模型门控的内容描述可重新启用的云端模式。

面向教室和实验室的智能火灾监控研究原型。当前基础功能支持两路 UVC 摄像头独立识别，由 YOLO 时序候选、千问多模态复核、站内预警和 ESP32 自动水泵控制组成。保留账号、教室与摄像头管理，人工审核和事件手动流转已移除。

硬件接线、固件与配置从 [双 UVC + ESP32 自动喷水](docs/runbooks/esp32-pump.md) 开始。

协作训练从 [模型训练协作](docs/training/collaboration.md) 开始。仓库包含代码和训练工具，不包含数据集、模型权重或本地密钥。

## Repository layout

```text
apps/
  api/          Spring Boot business API
  inference/    Python inference and event workers
  web/          Vue 3 operator console
contracts/      OpenAPI and versioned event schemas
infra/          Docker Compose and service configuration
ml/             AutoDL dataset preparation, audit, training, and evaluation tools
scripts/        Windows bootstrap, preflight, start, and stop scripts
docs/           Architecture, plans, runbooks, and test reports
```

## Development principles

- Contract first: OpenAPI and event schemas are the shared source of truth.
- Media and business events are separate: video uses MediaMTX; alerts use Spring WebSocket.
- The browser never receives raw RTSP credentials or cloud API secrets.
- The inference worker never writes the business database directly.
- 云端复核模式要求正向复核才发布确认预警及喷水指令；本地时序模式见上述运行说明。
- Demo events must be visibly labeled as tests; never create real fire or smoke for a demonstration.

## Target demo environment

- Windows 11 Pro
- NVIDIA GeForce RTX 5060 Laptop GPU, 8GB VRAM
- 16GB RAM
- Two UVC USB cameras connected to Windows; ESP32 CH340 over USB serial
- Native Windows FFmpeg/Python inference; Docker Compose for supporting services

## Competition prototype scope

前端主入口为火灾识别与预警、大模型研判、自动喷水，保留教室与摄像头及账号登录。
两个 UVC 摄像头可同时独立识别，可绑定同一教室两个视角，也可分属不同教室。
在教室页分别选择设备编号并启动，监控页切换画面；停止一只不影响另一只。
识别记录保留关键帧、大模型结果与时间线，人工确认、处置、解决和误报按钮及写接口已移除。
单只泵按配置覆盖一个教室，正向 AI 复核后自动发串口指令，默认 5 秒、冷却 60 秒。
页面显示控制器回执、持久化指令记录和紧急停止锁定；没有水流反馈，不能据此确认实际出水。
新教室、已有教室、账号与历史预警继续保留；有历史预警的教室删除时仍只归档。
默认管理员开发密码为 `123456`。实际加载的权重取决于本地配置；新交付 YOLO26s 尚未部署。

## Current MVP

- Spring Boot control plane with JWT/RBAC, zones, cameras, read-only incident history, pump status/stop proxy, Flyway, WebSocket and Redis Stream ingestion;
- Vue 3 operator console with real/mock API modes, local annotated stream, two-camera device binding, automatic suppression status and semantic review;
- Python 3.11 inference service with bounded latest-frame queues, N/M temporal evidence, Redis publishing, Ultralytics live inference and Qwen 3.7 Plus structured-output integration;
- local MySQL, Redis, MinIO and MediaMTX infrastructure;
- repeatable Windows bootstrap/start/verify/stop scripts.

## Safe local demo

Docker Desktop and Clash Verge TUN should be running. The script uses system networking and never stores a proxy endpoint.

本机摄像头控制：完成服务启动后，在「教室与摄像头」添加前置或 USB 摄像头，刷新并选择实际设备，绑定教室后点击「接入 → 启动识别」。同一设备编号不可重复启动，最多同时两路。虚拟摄像头也占用编号，USB 不一定为 1。
单独启动等待页面选设备的推理服务可执行 `scripts/windows/start-inference.ps1`（不加参数）；保留 `-LiveCamera` 可继续自动启动。
控制接口为 `GET /api/v1/cameras/local-devices`、`POST /api/v1/cameras/{id}/start` 和 `POST /api/v1/cameras/local-stop`。
控制请求经业务 API 验证登录和权限后转发；可在服务器设置 `INFERENCE_CONTROL_TOKEN`，Java/Python 两端保持一致，该值不发送到浏览器。

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\setup-local-yolo.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\windows\start-demo.ps1 -LiveInference -SelectCameras
```

The first run prepares isolated dependencies and starts the stack. Select and bind each UVC camera in Rooms, then start recognition; the worker loads the archived `best.pt` on the RTX 5060. Existing room/camera bindings are preserved with `-SelectCameras`. Open `http://127.0.0.1:5173` and sign in with the development-only account shown on the login page. Python owns the camera in live mode, so FFmpeg ingest is intentionally not started at the same time.

To enable Qwen analysis, put `DASHSCOPE_API_KEY` only in the ignored local `.env`. It is called once after temporal confirmation, never for every frame. Stop everything with:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\stop-demo.ps1
```

## Verification

```powershell
# API
cd .\apps\api
..\..\.tools\apache-maven-3.9.11\bin\mvn.cmd test

# Inference
cd ..\inference
$env:PYTHONPATH = Join-Path (Get-Location) "src"
.\.conda\python.exe -m pytest -q
.\.conda\python.exe -m ruff check src tests

# Web
cd ..\web
npm run test
npm run lint -- --quiet
npm run build
```

## Single-camera YOLO check

The trained `best.pt` can be tested directly with the integrated Windows camera without Docker, Redis, SMS, or a cloud VLM call:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\setup-local-yolo.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\test-single-camera.ps1
```

Press `Q` or `Esc` in the preview window to stop. See `docs/runbooks/single-camera-yolo.md` for parameters, output meanings, and troubleshooting.

Detailed plans live in `docs/plans/`. The step-by-step cloud training guide is
`docs/plans/AutoDL-初步火灾识别模型训练说明书.md`; current delivery state is tracked in
`docs/project/STATUS.md` and the Windows runbook is in `docs/runbooks/windows-demo.md`.

## Honest milestone boundary

Each of the two independent camera chains follows: DirectShow camera → local YOLO overlays → 3/5 local candidate → three-frame Qwen 3.7 Plus verification gate → confirmed Redis/Spring incident → private MinIO evidence JPEG → WebSocket/browser. The current strict gate holds candidates when cloud verification fails or does not confirm visible physical fire/smoke. Positive live verification can trigger the configured room pump over ESP32 USB serial. SMS and cross-camera fusion are disabled. Firmware logic is compiled and tested on the host; ESP32 board compilation, flashing, real camera capture, wiring, pressure and water flow still require hardware acceptance. This is a research prototype and must not replace certified fire alarm equipment or become the only life-safety notification path.
