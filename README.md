# 火情监控

教室火情检测、四路定位和告警研判。后端是 `apps/server` 的 FastAPI 服务。前端是 `apps/web` 的 Vue 3、TypeScript、Vite 和 Element Plus。检测、时序确认、四摄定位、千问分析和 ESP32 串口泵在 `apps/inference`，由后端调用。

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

登录。教室管理，含最多 4 路摄像头绑定、标定和平面图。摄像头管理。实时监控，选定教室后四宫格，显示检测框和状态。告警研判，含四路关键帧、大模型分析、平面图火点、处置记录和手动重跑分析。系统配置只读，密钥打码。角色只有管理员和值班员。

## 定位和告警

每路标定包含 3×3 内参、畸变，以及至少 4 个控制点（`world_m` 和 `pixel`）。告警时按 `localize_frames` 的 manifest 组织这些数据和检测得到的 `source`（像素、协方差、可靠度），调用 `apps/inference` 里的 `localize_frames`。火用检测框底边中点，烟用框中心。返回 `ESTIMATED` 时告警写入 `xyz`、`covariance`、`condition_number` 和 `support_camera_ids`，平面图标出火点。返回 `UNOBSERVABLE` 时不写坐标，平面图不标点。

千问在配置打开时分析告警关键帧。短信发给 `config.json` 里的固定名单，带教室名、类型和时间，有开关和冷却时间。喷水泵沿用原有串口行为，监控页可以紧急停泵。

控制点和平面图比例需要在现场测量后录入。

## config.json

复制 `config.example.json`。未知字段会被拒绝。

| 部分 | 内容 |
|---|---|
| `server` | 监听地址、端口、允许的前端来源 |
| `database` | MySQL。库名、用户和密码要与 `compose.yaml` 一致。表在后端启动时创建 |
| `minio` | 证据图和平面图。`endpoint` 不带 `http://`。`secure` 为 false 时走 HTTP |
| `mediamtx` | RTSP 根地址、WHEP 根地址、各监听端口、生成的配置路径、FFmpeg 和 MediaMTX 程序路径 |
| `llm` | 千问兼容接口的开关、`base_url`、`model`、`api_key` |
| `sms` | 阿里云短信的开关、访问密钥、签名、模板、固定收件人、冷却秒数。模板变量是 `room`、`type`、`time` |
| `model` | 权重路径、版本名、边长、设备、火焰和烟雾阈值 |
| `temporal` | 时序确认的 `n`、`m`、`candidate_n`、清空帧数和冷却毫秒。要求 `candidate_n <= n <= m` |
| `localization` | 控制点像素噪声 `landmark_sigma_px`，多路观测时间窗 `window_ms` |
| `pump` | 开关、串口、覆盖的教室 id、时长、冷却、本地确认门槛、是否要求千问、命令记录文件 |
| `auth` | JWT 密钥、有效期、启动时写入的账号。角色只能是 `admin` 或 `operator` |
| `cameras` | 新建摄像头未填帧率时使用的 `default_fps` |
| `timezone` | 短信使用的时区，例如 `Asia/Shanghai` |

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
