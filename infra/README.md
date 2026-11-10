# Infrastructure

The supporting stack runs with Docker Compose while camera capture and GPU inference run natively on Windows.

## Services

- MySQL: `127.0.0.1:3306`
- MinIO: `127.0.0.1:9000`, console `9001`

MediaMTX 由 `scripts/windows/start-streams.ps1` 在本机启动。端口和账号以 `config.json` 为准，Compose 里的默认值和 `config.example.json` 一致。数据目录默认是 `D:\FireMonitoringData`。

```powershell
docker compose up -d
docker compose ps
```

