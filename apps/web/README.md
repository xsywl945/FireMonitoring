# 燧巡前端控制台

Vue 3 + TypeScript 的火灾监控前端 MVP。页面包含登录、运行总览、双视角实时监控、区域与摄像头管理、事件列表、事件处置台和系统健康。

## 本地开发

```powershell
Copy-Item .env.example .env
npm install
npm run dev
```

默认 `VITE_USE_MOCKS=true`，无需启动后端即可使用演示账号 `admin / FireAdmin123!` 浏览全部流程。将其改为 `false` 后，前端会按照 `contracts/openapi/fire-monitoring-v1.yaml` 请求 Spring Boot 服务。

## 验证

```powershell
npm run test
npm run build
```

## 视频播放

前端通过短期流票据获取 WHEP 与 HLS 地址，优先使用 WebRTC；建连失败后自动使用 HLS。摄像头的真实 RTSP 地址和凭据不进入浏览器。
