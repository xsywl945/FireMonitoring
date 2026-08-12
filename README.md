# Fire Monitoring

面向教室和实验室的智能火灾监控研究原型。当前里程碑采用单摄像头，由实时视频、YOLO 推理、单摄时序证据、千问多模态语义研判、站内预警和人工处置组成；双摄融合为后续扩展。

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

## Current MVP

- Spring Boot control plane with JWT/RBAC, zones, cameras, incident workflow, Flyway, WebSocket and Redis Stream ingestion;
- Vue 3 operator console with real/mock API modes, local annotated stream, device binding, incident handling and health views;
- Python 3.11 inference service with bounded latest-frame queues, N/M temporal evidence, Redis publishing, Ultralytics live inference and Qwen 3.7 Plus structured-output integration;
- local MySQL, Redis, MinIO and MediaMTX infrastructure;
- repeatable Windows bootstrap/start/verify/stop scripts.

## Safe local demo

Docker Desktop and Clash Verge TUN should be running. The script uses system networking and never stores a proxy endpoint.

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

The single-camera chain is integrated: DirectShow camera → local YOLO overlays → 3/5 temporal confirmation → Redis → Spring incident → private MinIO evidence JPEG → optional Qwen 3.7 Plus analysis → WebSocket/browser. SMS and dual-camera fusion are intentionally disabled. This is a research prototype and must not replace certified fire alarm equipment or become the only life-safety notification path.
