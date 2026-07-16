# Infrastructure

The supporting stack runs with Docker Compose while camera capture and GPU inference run natively on Windows.

## Services

- MySQL: `127.0.0.1:3306`
- Redis: `127.0.0.1:6379`
- MinIO: `127.0.0.1:9000`, console `9001`
- MediaMTX: RTSP `8554`, HLS `8888`, WHEP `8889`, playback `9996`, API `9997`

All published ports bind to localhost. Persistent data defaults to `D:\FireMonitoringData`.

Copy `.env.example` to `.env` and replace every `change-*` value before starting services.

```powershell
docker compose up -d
docker compose ps
```

