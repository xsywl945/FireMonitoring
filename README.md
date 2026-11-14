# 火情监控

教室火情检测、多路定位和告警研判。后端是 `apps/server` 的 FastAPI 服务。前端是 `apps/web` 的 Vue 3、TypeScript、Vite 和 Element Plus。时序确认、几何定位、千问客户端和 ESP32 水泵协议在 `apps/inference`，由后端在同一进程里调用。

实时画面进入 MediaMTX。浏览器使用 WebRTC（WHEP）播放。检测从 MediaMTX 的 RTSP 读流，不直接占用摄像头。USB 摄像头由 FFmpeg 推流，网络摄像头由 MediaMTX 拉 RTSP。

接口契约是运行中的 OpenAPI：`http://127.0.0.1:8080/openapi.json`。前端类型在 `apps/web/src/api/types.ts`。

仓库里没有 Java 后端，没有 Redis，也没有旧的前端环境变量。`docs/plans/` 和部分运行记录写的是更早的方案，启动以本文为准。

## 权重

模型权重不在 Git 仓库里。把微调权重放到 `models/yolo26s-ft-2026-11-04/best.pt`。`config.example.json` 的 `model.path` 指向这个文件。火焰阈值 0.30，烟雾阈值 0.35。低于对应阈值的框不进入时序，也不作为该类别的定位观测。

## Windows 启动

需要 Python 3.11、Node.js、FFmpeg、MediaMTX 的 Windows 程序和 Docker Desktop。`ffmpeg` 与 `mediamtx` 要在 PATH 里，或者把绝对路径写进 `config.json`。

```powershell
copy config.example.json config.json
```

按本机修改 `config.json`。这个文件含密钥，不要提交。

```powershell
docker compose up -d
powershell -ExecutionPolicy Bypass -File scripts\windows\bootstrap.ps1
powershell -ExecutionPolicy Bypass -File scripts\windows\start-server.ps1
powershell -ExecutionPolicy Bypass -File scripts\windows\start-web.ps1
```

`docker compose` 只启动 MySQL 和 MinIO。浏览器打开 `http://127.0.0.1:5173`，用 `config.json` 里的账号登录。先建教室和摄像头，再启动推流：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\start-streams.ps1
```

这个脚本按数据库里的摄像头写出 `runtime/mediamtx.yml`，启动 MediaMTX，并对每路 USB 摄像头启动 FFmpeg，推到 `rtsp_base/{stream_key}`。改了摄像头之后重新运行它。

停止脚本拉起的进程：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\stop.ps1
```

它不停止 Docker。数据库和对象存储用 `docker compose stop`。

开发时可以在仓库根目录执行 `python -m fire_monitoring`。前端在 `apps/web` 执行 `npm run dev`。`npm run build` 会先做类型检查再打包，Vite 从仓库根的 `config.json` 读取服务地址。

## 页面

登录。教室管理，含最多 4 路摄像头绑定、标定和平面图。未标定的绑定在教室详情里标红。摄像头管理。实时监控，选定教室后四宫格，显示检测框和状态。告警研判，含关键帧、大模型分析、燃烧物、是否有人、平面图火点、处置记录和手动重跑分析。任意页面都会通过 WebSocket 弹出告警并播放提示音。系统配置只读，密钥打码。角色只有管理员和值班员。

## 现场需要做的事

每路摄像头至少录入 4 个控制点：世界坐标 `world_m`（米）和对应像素 `pixel`。内参是 3×3，畸变按 OpenCV 的 `k1, k2, p1, p2, k3`。世界坐标原点由现场标定物决定，程序不假定教室某个角。

平面图要上传图片，并填写原点在图上的像素、原点的世界坐标 X/Y，以及每像素对应多少米。图上 X 向右、Y 向上，像素 u 向右、v 向下。火点按下面两式画：

```text
u = origin_px[0] + (X - origin_world_x) / meters_per_pixel
v = origin_px[1] - (Y - origin_world_y) / meters_per_pixel
```

每路一个采集线程，只保留最新帧，并按 2 fps 留一段环形缓冲。检测线程把到点的各路最新帧一批送进 YOLO，速度不超过该路 `target_fps`。检测线程只发出「已确认」事件。定位、千问、短信、水泵在各自的线程里处理。检测线程一旦抛错，进程退出，`/api/v1/health` 在退出前返回 503。

检测框变成定位观测的规则：火用框底边中点，烟用框中心。协方差取框宽、框高的四分之一作为标准差，写在对角线上。可靠度用置信度，并限制在 0.001 到 0.999，避免取 0 或 1。像素会限制在画面内。定位直接使用这些观测，不再把告警图片重新送进模型。至少 2 路同时有标定和窗口内观测才做几何定位，最多 4 路。返回 `ESTIMATED` 时告警写入 `xyz`、`covariance`、`condition_number` 和 `support_camera_ids`，平面图标出火点。不足 2 路或几何上不可观测时状态是 `UNOBSERVABLE`，告警、短信和水泵照常进行，平面图不标点。从确认到 WebSocket 弹出之间的毫秒数写在日志里，logger 名是 `fire_monitoring.alerts`。

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

证据图和平面图。`endpoint` 不带 `http://`，例如 `127.0.0.1:9000`。`secure` 为 false 时走 HTTP。`access_key` 和 `secret_key` 对应 MinIO 的 root 用户和密码。`bucket` 不存在时后端会创建。

### mediamtx

| 字段 | 含义 |
|---|---|
| `rtsp_base` | 推理和 FFmpeg 使用的 RTSP 根地址，路径是 `/{stream_key}` |
| `whep_base` | 浏览器 WebRTC 根地址，播放地址是 `/{stream_key}/whep` |
| `rtsp_address`、`hls_address`、`webrtc_address`、`webrtc_udp_address`、`api_address`、`playback_address` | 写进生成的 MediaMTX 配置的监听地址 |
| `config_path` | 生成的 `mediamtx.yml` 路径 |
| `ffmpeg_path` | FFmpeg 可执行文件 |
| `mediamtx_path` | MediaMTX 可执行文件 |

### llm

千问兼容接口。`enabled` 为 true 时，告警确认后在独立线程里把四路关键帧、火焰框放大图以及事件前后画面交给千问。提示词版本是 `fire-evidence-v4`。模型只返回燃烧物、疑似原因、带电设备、液体、油锅、金属粉末、人员、场景、烟和不确定项，不选择灭火剂。返回字段由本地模型校验，不合法就记为失败。研判页可以手动重跑。`pump.require_vlm` 为 true 时，水泵等到研判结果：看见火或烟才允许喷水，规则表禁止用水时拒绝喷水。`base_url`、`model`、`api_key` 是 DashScope 兼容模式的地址、模型名和密钥。超时 25 秒。规则表在 `config/fire_rules.json`。

### sms

告警研判完成后发给 `recipients` 里的固定号码。模板变量是 `location`（教室名）、`level`（Ⅰ级到Ⅳ级）、`method`（建议灭火方式）。三个变量都不超过 35 个字符。正文草稿见 [短信模板 v2](docs/sms/aliyun-template-v2.md)。`sign_name`、`template_code`、`access_key_id`、`access_key_secret` 是阿里云短信参数。`enabled` 为 false 或名单为空则不发送。`cooldown_seconds` 是同一教室两次短信的最短间隔。

### model

| 字段 | 含义 |
|---|---|
| `path` | 权重文件，当前为 `models/yolo26s-ft-2026-11-04/best.pt`。文件不在 Git 仓库里 |
| `version` | 写入告警和泵事件的模型版本名 |
| `imgsz` | 推理边长 |
| `device` | `0` 表示第一块 GPU，`cpu` 表示 CPU。不是 `cpu` 时使用半精度 |
| `thresholds.fire` | 火焰置信度，当前 0.30。低于此值不进入时序，也不作为火的观测 |
| `thresholds.smoke` | 烟雾置信度，当前 0.35 |

检测器的初始过滤取 `thresholds.fire` 和 `thresholds.smoke` 中较低的那个，再按类别阈值丢掉不够的框。

### temporal

时序确认按类别分开。最近 `m` 帧里有 `n` 帧达到该类别阈值则确认。达到 `candidate_n` 帧进入疑似。连续 `clear_frames` 帧没有目标后，已确认进入冷却，疑似回到正常。`cooldown_ms` 是冷却时长。要求 `candidate_n <= n <= m`。

### localization

| 字段 | 含义 |
|---|---|
| `landmark_sigma_px` | 控制点像素噪声，大于 0，用于姿态协方差 |
| `window_ms` | 多路观测凑齐的时间窗，单位毫秒 |

### panel

报警节点串口。`enabled` 为 true 时必须填写 `serial_port`。连接后主机发送 `MODE GREEN`，并每 0.5 秒发送 `PING`。3 秒没有主机报文时，固件自己变成黄红交替。协议见 `contracts/panel-serial-v2.md`。

### pump

`enabled` 为 true 时必须填写 `serial_port` 和 `zone_id`。`zone_id` 是覆盖的教室 id，不是摄像头 id。确认告警后向执行节点发送 `FIRE_ACTUATOR_V2` 的 `RUN` 指令，持续 `duration_ms` 毫秒。BOOT 强制喷水已删除。接线见 `docs/hardware/wiring.md`。

`require_vlm` 为 false 时，用本地火焰确认：分数不低于 `local_min_confidence`，有效帧数不少于 `local_min_frames`。为 true 时还要求千问证据校验通过，并且看见火或烟；规则表禁止用水时不发 `RUN`。`max_evidence_age_seconds` 是从取证到发指令允许的最大延迟，超出则不启动。`cooldown_seconds` 是两次启动的最短间隔。`journal_path` 是命令记录的 SQLite 文件。监控页可以紧急停泵。

### auth

| 字段 | 含义 |
|---|---|
| `jwt_secret` | 登录令牌签名密钥，至少 16 个字符 |
| `jwt_expiration_seconds` | 令牌有效期，单位秒 |
| `users` | 启动时写入数据库的账号。`role` 只能是 `admin`（管理员）或 `operator`（值班员） |

管理员可以改教室、摄像头、标定和平面图，并查看系统配置。值班员可以看监控、告警、记录处置和重跑分析。

### cameras

`default_fps`：新建摄像头时帧率留空使用的默认值。USB 推流和检测按摄像头自己的 `target_fps`。

### timezone

短信使用的时区，例如 `Asia/Shanghai`。

## 测试

```powershell
python -m pip install -e apps/inference -e apps/server[dev]
python -m pytest apps/server/tests
```

前端在 `apps/web`：

```powershell
npm run build
```

实机检测还要安装 `apps/server` 的 `detect` 可选依赖，`bootstrap.ps1` 会安装它。
