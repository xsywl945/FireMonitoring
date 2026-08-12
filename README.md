# Fire Monitoring

面向教室和实验室的双视角智能火灾监控研究原型。系统由实时媒体、YOLO推理、单摄时序证据、双摄决策融合、多模态语义研判、预警和人工处置闭环组成。

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
- Vue 3 operator console with real/mock API modes, dual-view player, device binding, incident handling and health views;
- Python 3.11 inference service with bounded latest-frame queues, N/M temporal evidence, 500 ms dual-camera fusion, Redis publishing, mock replay, optional Ultralytics and Qwen3-VL-Plus adapters;
- local MySQL, Redis, MinIO and MediaMTX infrastructure;
- repeatable Windows bootstrap/start/verify/stop scripts.

## Safe local demo

Docker Desktop and Clash Verge TUN should be running. The script uses system networking and never stores a proxy endpoint.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\start-demo.ps1 -SkipCamera
```

The first run creates isolated Maven/Python/Node dependencies, starts the stack, creates a default classroom, and publishes a deterministic test incident. Open `http://127.0.0.1:5173` and sign in with the development-only account shown on the login page.

To include the integrated camera ingest (MediaMTX only at this milestone), omit `-SkipCamera`. Stop everything with:

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

The management frontend/backend, event contracts, safe replay, media ingest and inference decision core are implemented. DirectShow decoding from one local camera into the trained fire/smoke model and the existing temporal pipeline is implemented as an isolated test command. Web video overlays, the MediaMTX-to-YOLO live worker, evidence clip extraction, Alibaba SMS delivery/receipts and cloud VLM orchestration remain subsequent milestones. The Qwen adapter exists and fails safely when no API key is configured.
