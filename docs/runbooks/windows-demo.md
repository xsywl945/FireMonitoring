# Windows 本地演示运行手册

## 前置条件

- Docker Desktop 已启动；
- Clash Verge TUN 可用；项目不设置固定代理；
- Java 17、Node.js、Conda、FFmpeg 和 Git 可用；
- D 盘建议至少保留 20 GB 空间。

## 首次启动

```powershell
cd C:\Users\xsywl\Desktop\FireMonitoring
powershell -ExecutionPolicy Bypass -File .\scripts\windows\start-demo.ps1 -SkipCamera
```

首次启动会在仓库忽略目录中准备 `.tools`、`apps/inference/.conda` 和 `apps/web/node_modules`。`.env` 由 `.env.example` 复制且不提交 Git；真实云密钥只写入 `.env`。

默认使用确定性安全回放验证完整事件链。添加 `-LiveInference` 会启动空闲的实时服务边界，但在 M2 接入 YOLO 摄像头循环前不会产生检测事件。

## 摄像头与流媒体

列出 DirectShow 摄像头：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\list-cameras.ps1
```

使用集成摄像头启动完整演示时，不传 `-SkipCamera`。RTSP 发布地址为 `rtsp://127.0.0.1:8554/raw/integrated`，浏览器播放由 API 生成 WHEP/HLS 地址。

## 健康检查

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\verify-demo.ps1
docker compose ps -a
```

日志位于 `runtime/logs/`，PID 位于 `runtime/pids/`。这些目录不提交 Git。

## 停止与恢复

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\stop-demo.ps1
```

异常中断后可再次运行停止脚本清理本项目进程。数据保留在 `D:\FireMonitoringData`；`docker compose down` 不删除持久数据。

## 故障定位顺序

1. 执行 `preflight.ps1`；
2. 检查 `docker compose ps -a`；
3. 检查 `runtime/logs/api.err.log`、`inference.err.log` 和 `web.err.log`；
4. 验证 8080、8091、5173、6379、8554 端口是否被其他进程占用；
5. 仅在下载失败时检查 Clash TUN/DNS，不向仓库写代理端口。
