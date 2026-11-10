# 火情监控

教室火情检测、四路定位和告警研判。后端是一个 FastAPI 服务，前端是 Vue 3。实时画面统一进 MediaMTX，浏览器用 WebRTC（WHEP）播放，检测从 MediaMTX 的 RTSP 读流。

接口契约是运行中的 OpenAPI：`http://127.0.0.1:8080/openapi.json`。前端类型写在 `apps/web/src/api/types.ts`。`docs/` 里的旧说明只作历史参考，启动以本文为准。

## Windows 启动

准备：Python 3.11、Node.js、FFmpeg、[MediaMTX](https://github.com/bluenviron/mediamtx/releases) Windows 版、Docker Desktop。把 `ffmpeg.exe` 和 `mediamtx.exe` 放到 PATH，或在 `config.json` 里写绝对路径。

```powershell
copy config.example.json config.json
# 按本机修改 config.json。这个文件含密钥，不要提交。

docker compose up -d
powershell -ExecutionPolicy Bypass -File scripts\windows\bootstrap.ps1
powershell -ExecutionPolicy Bypass -File scripts\windows\start-server.ps1
powershell -ExecutionPolicy Bypass -File scripts\windows\start-web.ps1
```

浏览器打开 `http://127.0.0.1:5173`，用 `config.json` 里的账号登录。先建教室和摄像头，再启动推流：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\start-streams.ps1
```

`start-streams.ps1` 读取数据库里的摄像头，写出 `runtime/mediamtx.yml`，启动 MediaMTX，并对每路 USB 摄像头启动 FFmpeg 推到 `rtsp_base/{stream_key}`。网络摄像头由 MediaMTX 按 RTSP 地址拉流。改了摄像头之后重新运行这个脚本。

停止脚本拉起的进程：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\stop.ps1
```

`stop.ps1` 不停止 Docker。数据库和对象存储用 `docker compose stop`。

开发时后端也可以在仓库根目录执行 `python -m fire_monitoring`。前端在 `apps/web` 执行 `npm run dev`。构建执行 `npm run build`，Vite 从仓库根的 `config.json` 读取服务地址做代理。

## 现场需要做的事

每路摄像头至少录入 4 个控制点：世界坐标 `world_m`（米）和对应像素 `pixel`。内参是 3×3，畸变按 OpenCV 的 `k1, k2, p1, p2, k3`。世界坐标原点由现场标定物决定，程序不假定教室某个角。

平面图要上传图片，并填写原点在图上的像素、原点的世界坐标 X/Y，以及每像素对应多少米。图上 Y 轴向上、像素 v 向下，火点纵向位置按 `origin_px[1] - (Y - origin_world_y) / meters_per_pixel` 画。

检测框变成定位观测的规则：火用框底边中点，烟用框中心；协方差取框宽、框高的四分之一作为标准差；可靠度用置信度，并限制在 (0, 1)。时间窗内至少两路有效观测才调用 `locate()`。

## config.json

复制 `config.example.json`。未知字段会被拒绝。密钥只留在本机文件里。

### server

| 字段 | 含义 |
|---|---|
| `host` | 后端监听地址 |
| `port` | 后端端口 |
| `cors_origins` | 允许的前端来源 |

### database

MySQL 连接。`name`、`user`、`password` 要和 `compose.yaml` 里的库一致。表在后端启动时创建。

### minio

证据图和平面图。`endpoint` 不带 `http://`，例如 `127.0.0.1:9000`。`secure` 为 `false` 时走 HTTP。`access_key` / `secret_key` 对应 MinIO 的 root 用户和密码。`bucket` 不存在时后端会创建。

### mediamtx

| 字段 | 含义 |
|---|---|
| `rtsp_base` | 推理和 FFmpeg 使用的 RTSP 根地址，路径是 `/{stream_key}` |
| `whep_base` | 浏览器 WebRTC 根地址，播放地址是 `/{stream_key}/whep` |
| `rtsp_address` / `hls_address` / `webrtc_address` / `webrtc_udp_address` / `api_address` / `playback_address` | 写进生成的 MediaMTX 配置的监听地址 |
| `config_path` | 生成的 `mediamtx.yml` 路径 |
| `ffmpeg_path` | FFmpeg 可执行文件 |
| `mediamtx_path` | MediaMTX 可执行文件 |

### llm

千问兼容接口。`enabled` 为 true 时，告警确认后自动分析四路关键帧，研判页也可以手动重跑。`base_url`、`model`、`api_key` 是 DashScope 兼容模式的地址、模型名和密钥。

### sms

告警确认后发给 `recipients` 里的固定号码。模板变量是 `room`（教室名）、`type`（火焰 / 烟雾 / 火焰和烟雾）、`time`（`timezone` 下的本地时间）。`sign_name`、`template_code`、`access_key_id`、`access_key_secret` 是阿里云短信参数。`enabled` 为 false 或名单为空则不发送。`cooldown_seconds` 是同一教室两次短信的最短间隔。

### model

| 字段 | 含义 |
|---|---|
| `path` | 权重文件，当前为 `models/yolo26s-ft-2026-11-04/best.pt` |
| `version` | 写入告警和泵事件的模型版本名 |
| `imgsz` | 推理边长 |
| `device` | `0` 表示第一块 GPU，`cpu` 表示 CPU |
| `thresholds.fire` | 火焰置信度，当前 0.30。低于此值不进入时序，也不作为火的观测 |
| `thresholds.smoke` | 烟雾置信度，当前 0.35 |

检测器的初始过滤取两者中较低的那个，再按类别阈值丢掉不够的框。

### temporal

时序确认：最近 `m` 帧里有 `n` 帧达到该类别阈值则确认；`candidate_n` 帧进入疑似。`clear_frames` 帧没有目标后，已确认进入冷却，疑似回到正常。`cooldown_ms` 是冷却时长。要求 `candidate_n <= n <= m`。

### localization

| 字段 | 含义 |
|---|---|
| `landmark_sigma_px` | 控制点像素噪声，用于姿态协方差 |
| `window_ms` | 多路观测凑齐的时间窗 |

### pump

保持原来的串口泵行为，不新增控制方式。`enabled` 为 true 时必须填写 `serial_port` 和 `zone_id`。`zone_id` 是覆盖的教室 id。确认告警后，若本地火焰分数和帧数达到 `local_min_confidence`、`local_min_frames`，向 ESP32 发送原来的 `RUN` 指令，持续 `duration_ms`。`require_vlm` 为 true 时还要求千问确认，且置信度不低于 `min_confidence`。`max_evidence_age_seconds` 是证据允许的最大延迟。`cooldown_seconds` 是两次启动间隔。`journal_path` 是命令记录的 SQLite 文件。监控页可以紧急停泵。

### auth

| 字段 | 含义 |
|---|---|
| `jwt_secret` | 登录令牌签名密钥，至少 16 个字符 |
| `jwt_expiration_seconds` | 令牌有效期 |
| `users` | 启动时写入数据库的账号。`role` 只能是 `admin`（管理员）或 `operator`（值班员） |

管理员可以改教室、摄像头、标定和平面图，并查看系统配置。值班员可以看监控、告警、记录处置和重跑分析。

### cameras

`default_fps`：新建摄像头时帧率留空使用的默认值。USB 推流和检测按摄像头自己的 `target_fps`。

### timezone

短信时间和界面以外的本地化时间，例如 `Asia/Shanghai`。

## 目录

```text
apps/server    FastAPI：教室、摄像头、流、检测、定位、告警、分析、短信、证据、泵、登录、配置
apps/web       Vue 3 前端
apps/inference 被服务复用的检测、时序、千问和串口泵实现
ml/scripts/multiview_geometry.py  原定位算法，服务内有一份相同实现
config.example.json
scripts/windows
```

后端测试：

```powershell
python -m pip install -e apps/inference -e apps/server[dev]
python -m pytest apps/server/tests
```
