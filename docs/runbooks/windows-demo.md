# Windows 单摄完整系统运行手册

## 当前集成范围

当前可运行链路为：笔记本前置摄像头 → RTX 5060 上的 YOLO11s → 单摄 3/5 帧本地候选 → 最近 3 帧 Qwen 3.7 Plus 复核 → 复核通过后发布正式事件 → Redis → Spring Boot → 私有 MinIO 关键帧 → WebSocket 与 Vue 控制台。

短信和第二路摄像头未启用。本系统是研究原型，不能替代认证火灾报警器，也不能作为唯一生命安全通知链路。

## 前置条件

- Docker Desktop 已启动；
- Clash Verge TUN 可用；项目不写死代理地址；
- 摄像头没有被会议软件占用；
- Java 17、Node.js、Conda、FFmpeg 和 Git 可用；
- 模型存在于 `data/training-archive/2026-08-12-yolo11s-primary-v2/models/deployment/best.pt`。

## 首次准备

在 PowerShell 中运行：

```powershell
cd C:\Users\xsywl\Desktop\FireMonitoring
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\setup-local-yolo.ps1
```

如需启用千问，只在被 Git 忽略的 `.env` 中填写以下一行。不要把密钥放进源码、命令历史、截图或报告；已经发到聊天里的密钥应先轮换。

```dotenv
DASHSCOPE_API_KEY=替换为轮换后的新密钥
```

其余配置保持：

```dotenv
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DASHSCOPE_MODEL=qwen3.7-plus
INFERENCE_VLM_GATE_ENABLED=true
INFERENCE_VLM_GATE_MIN_CONFIDENCE=0.70
INFERENCE_VLM_GATE_FAIL_OPEN=false
SMS_DEMO_ARMED=false
```

## 启动完整单摄系统

首次启动不要使用 `-SkipBuild`：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\start-demo.ps1 -LiveInference
```

后续代码未变化时可加快启动：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\start-demo.ps1 -LiveInference -SkipBuild
```

打开 `http://127.0.0.1:5173`，使用登录页显示的本机开发账号。进入“实时监控”后应看到：

- 前置摄像头画面和 YOLO 检测框；
- 推理状态 `RUNNING`、模型版本、单帧耗时和处理帧数；
- 当前火焰/烟雾候选；
- YOLO 候选框，以及只有通过 3/5 帧规则和千问复核后才生成的正式预警事件。

实时模式下 Python 直接拥有摄像头，脚本不会同时启动 FFmpeg，避免设备争用。不要为了测试制造明火或烟雾；优先使用安全的视频/图片回放或正常场景观察。

## 千问调用策略

采用百炼 OpenAI 兼容 `chat/completions` 接口。YOLO 通过 3/5 帧规则后只调用一次：最近 3 个时序帧以内存 Base64 `data:image/jpeg` 发送，`enable_thinking=false`，要求 JSON Object 输出，并在本地做严格 Pydantic 校验。

当前为严格门控：只有 `hasVisibleFire` 或 `hasVisibleSmoke` 为真，且大模型置信度不低于 `0.70` 时才发布正式预警。未配置密钥会阻止实时推理服务就绪；API 超时、HTTP 错误、结构校验失败、低置信度或判断为屏幕内容/反光/蒸汽等情况只保留本地候选，不进入事故和站内通知链。若未来需要在断网时优先保证召回，可显式把 `INFERENCE_VLM_GATE_FAIL_OPEN` 改为 `true`，但这不符合当前“必须经过大模型研判”的要求。

系统不会启用模型内置网页搜索、代码解释器或其他工具，也不会逐帧调用 API。

该门控会引入云端延迟和断网漏报风险，只适用于科研演示，不能作为唯一生命安全链路或替代认证火灾报警器。

## 健康检查

```powershell
Invoke-RestMethod http://127.0.0.1:8091/api/v1/runtime
Invoke-RestMethod http://127.0.0.1:8091/api/v1/live/status
docker compose ps
```

正常时 `runtime.status` 为 `RUNNING`，`live/status.ready` 为 `true`。日志位于 `runtime/logs/`，重点查看 `inference.err.log`、`api.err.log` 和 `web.err.log`。

## 停止与恢复

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\stop-demo.ps1
```

停止脚本会关闭本项目进程和容器，但不删除持久数据。MySQL、Redis 和 MinIO 数据仍保留在 `D:\FireMonitoringData`。

若摄像头打不开，依次关闭相机/会议软件、运行停止脚本、确认 `runtime/pids/` 中没有残留进程，再重新启动。若下载或云 API 失败，再检查 Clash TUN、DNS 和 TLS；不要往仓库写本机代理端口。
