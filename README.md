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

Detailed plans live in `docs/plans/`.

