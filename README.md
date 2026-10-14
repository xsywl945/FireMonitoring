# Fire Monitoring

面向教室和实验室的智能火灾监控研究原型。当前里程碑采用单摄像头，由实时视频、YOLO 推理、单摄时序证据、千问多模态语义研判、站内预警和人工处置组成；双摄融合为后续扩展。

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
- Cloud multimodal analysis and SMS are asynchronous and may not block the base alarm.
- Demo events must be visibly labeled as tests; never create real fire or smoke for a demonstration.

## Target demo environment

- Windows 11 Pro
- NVIDIA GeForce RTX 5060 Laptop GPU, 8GB VRAM
- 16GB RAM
- One integrated camera and optional UVC USB camera
- Native Windows FFmpeg/Python inference; Docker Compose for supporting services

## Competition prototype scope

比赛版前端仅保留三个入口：火灾识别与预警、大模型研判、预警响应。
识别页展示实际画面和模型置信度；研判页展示已发布预警的多模态复核记录；
响应页支持确认、开始处置、解决和误报标注，并保留关键帧与时间线。
统计总览和健康页已移除；教室与摄像头页支持新建、编辑、删除及单摄绑定。
删除有历史预警的教室时仅归档，不删除预警。管理员默认密码为 `123456`。
本机摄像头接入窗口支持设备列表、启动识别与停止。前置和 USB 摄像头共用单摄推理链路。
网络摄像头需通过 MediaMTX 预览。
`GET /api/v1/incidents/analyses` 提供研判列表，不暴露证据存储地址。
界面采用简洁的浅色布局；模拟数据与实际服务明确标识。
本次不调整模型权重、识别阈值、训练流程或仓库目录。

## Current MVP

- Spring Boot control plane with JWT/RBAC, zones, cameras, incident workflow, Flyway, WebSocket and Redis Stream ingestion;
- Vue 3 operator console with real/mock API modes, local annotated stream, device binding, incident handling and semantic review;
- Python 3.11 inference service with bounded latest-frame queues, N/M temporal evidence, Redis publishing, Ultralytics live inference and Qwen 3.7 Plus structured-output integration;
- local MySQL, Redis, MinIO and MediaMTX infrastructure;
- repeatable Windows bootstrap/start/verify/stop scripts.

## Safe local demo

Docker Desktop and Clash Verge TUN should be running. The script uses system networking and never stores a proxy endpoint.

本机摄像头控制：完成服务启动后，在「教室与摄像头」添加前置或 USB 摄像头，刷新并选择实际设备，绑定教室后点击「接入 → 启动识别」。切换设备前点击停止。虚拟摄像头也占用编号，USB 不一定为 1。
单独启动等待页面选设备的推理服务可执行 `scripts/windows/start-inference.ps1`（不加参数）；保留 `-LiveCamera` 可继续自动启动。
控制接口为 `GET /api/v1/cameras/local-devices`、`POST /api/v1/cameras/{id}/start` 和 `POST /api/v1/cameras/local-stop`。
控制请求经业务 API 验证登录和权限后转发；可在服务器设置 `INFERENCE_CONTROL_TOKEN`，Java/Python 两端保持一致，该值不发送到浏览器。

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\setup-local-yolo.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\windows\start-demo.ps1 -LiveInference
```

The first run prepares isolated dependencies, starts the stack, creates/binds the integrated camera, and loads the archived `best.pt` on the RTX 5060. Open `http://127.0.0.1:5173` and sign in with the development-only account shown on the login page. Python owns the camera in live mode, so FFmpeg ingest is intentionally not started at the same time.

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

The single-camera chain is integrated: DirectShow camera → local YOLO overlays → 3/5 local candidate → three-frame Qwen 3.7 Plus verification gate → confirmed Redis/Spring incident → private MinIO evidence JPEG → WebSocket/browser. The current strict gate holds candidates when cloud verification fails or does not confirm visible physical fire/smoke. SMS and dual-camera fusion are intentionally disabled. This is a research prototype and must not replace certified fire alarm equipment or become the only life-safety notification path.
