# Python inference service

该目录是 Windows 原生算法进程的 MVP。它负责检测摘要、单摄 N/M 时序证据、500 ms
双摄决策融合、Redis Streams 事件发布和云端视觉研判适配；不管理用户、不写 MySQL，也不向
浏览器传输视频。

当前 MVP 可在没有 PyTorch、显卡或摄像头的环境中完整回放事件链。真正的摄像头/RTSP
采集和事件视频证据提取是后续集成项；队列与检测器边界已经固定，接入时不应改变共享事件契约。

## 目录

```text
src/fire_monitoring_inference/
  api.py                    Flask 健康与运行状态 API
  contracts.py              contracts/events/v1 的 Pydantic 映射
  frames.py                 保留最新帧的 1–3 帧有界队列
  temporal.py               单摄 NORMAL/SUSPECT/CONFIRMED/COOLDOWN
  fusion.py                 500 ms 双摄决策级融合
  pipeline.py               检测到 Redis 事件的编排
  replay.py                 确定性 JSONL 回放
  publisher.py              内存、标准输出、Redis Streams 发布器
  detectors/                Mock 与可选 Ultralytics 适配器
  vision/                   Qwen 3.7 Plus 严格结构化适配器
tests/                      时序、融合、Schema、回放与安全测试
```

## Python 3.11 隔离环境

不要安装到 Anaconda base。Windows PowerShell 示例：

```powershell
cd C:\Users\xsywl\Desktop\FireMonitoring\apps\inference
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
pytest
```

Clash Verge TUN 模式由系统接管网络，本服务不会写死 `HTTP_PROXY`。若 pip 无法联网，先检查
TUN/DNS 状态；不要把代理端口或云端密钥提交到仓库。

## 无 GPU 回放

下面的内置场景只回放检测元数据，不会打开摄像头或制造真实明火：

```powershell
fire-inference replay
fire-inference replay --publisher memory
fire-inference write-example .\runtime\demo.jsonl
fire-inference replay --input .\runtime\demo.jsonl
```

标准输出模式每行输出一个完整 JSON 事件。Redis 模式将事件写入
`monitoring.events`，每个 Stream entry 只有一个 `event` 字段，其值是完整的 v1 envelope：

```powershell
fire-inference replay --publisher redis
```

可用环境变量见 `.env.example`。`runtime/` 已由仓库 `.gitignore` 排除。

## 管理 API

```powershell
fire-inference serve
```

- `GET /healthz`：进程存活；
- `GET /readyz`：事件发布器可用性；
- `GET /api/v1/runtime`：状态、处理帧数、已发事件和确认事件数；
- `GET /api/v1/config`：脱敏后的有效配置。

联 Redis 启动使用 `fire-inference serve --redis`。管理 API 线程不承载视频解码或无限推理
循环；`--replay <jsonl>` 仅用于集成演示，并在独立后台线程运行。

## 接入 YOLO

`UltralyticsDetector` 延迟导入 Ultralytics，所以基础测试不需要 torch。RTX 5060 Laptop 的
PyTorch/CUDA wheel 应按项目计划单独安装并先验证 `torch.cuda.is_available()`；随后安装：

```powershell
python -m pip install "ultralytics>=8.3,<9"
```

训练权重的类别必须映射为小写 `fire`/`smoke`。适配器会丢弃未知类别，避免把 COCO 类别误发
为火灾事件。首轮参数以 `imgsz=640`、FP16、每路 5 FPS、batch 不超过 2 为基线。

## Qwen 3.7 Plus

密钥只从本机环境变量 `DASHSCOPE_API_KEY` 注入，默认模型为 `qwen3.7-plus`。适配器仅接受内存中的 `data:image/...`
URL，每个事件最多 3 张图，禁止远程 URL；输出必须通过禁止额外字段的 Pydantic 模型。超时、
HTTP 错误、JSON 错误或 Schema 错误都会返回 `FAILED` 和稳定错误码，绝不取消基础报警，
也不会伪造云端分析结果。

## 契约约束

Pydantic 字段序列化为共享契约要求的 camelCase。测试会同时校验：

- `contracts/events/v1/event-envelope.schema.json`
- `contracts/events/v1/payloads/detection-summary.schema.json`
- `contracts/events/v1/payloads/incident-confirmed.schema.json`
- `contracts/events/v1/payloads/vlm-analysis.schema.json`

修改公共字段前必须先修改共享契约并与 Spring Boot 消费端协调，不能只改本目录代码。
