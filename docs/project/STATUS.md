# 项目状态

更新日期：2026-11-13。当前运行方式以仓库根目录 [README](../../README.md) 为准。

## 现在的程序

后端是 `apps/server`，一个 FastAPI 进程。它负责登录、教室、摄像头、检测调度、告警、证据、短信和串口泵。数据库是 MySQL，证据图和平面图在 MinIO。没有 Redis，也没有 Java 服务。

前端是 `apps/web`，Vue 3、TypeScript、Vite 和 Element Plus。页面有登录、教室（最多绑定 4 路摄像头，并录入标定和平面图）、摄像头、实时监控四宫格、告警研判和只读系统配置。角色分为管理员和值班员。

实时画面走 MediaMTX。浏览器用 WebRTC（WHEP）播放。USB 由 `scripts/windows/start-streams.ps1` 调 FFmpeg 推流，网络摄像头拉 RTSP。检测读 MediaMTX 的 RTSP。

定位在 `apps/inference/src/fire_monitoring_inference/localization.py` 的 `localize`，几何计算在同目录的 `multiview_geometry.py`。标定使用 `solvePnPRansac` 和 `solvePnPRefineLM`，定位使用 Nelder-Mead 和离群混合模型。告警确认后用检测框已经得到的观测做几何，不再重新检测。2 到 4 路有标定和观测即可。`ESTIMATED` 写入坐标、协方差、条件数和支持摄像头。不足 2 路时为 `UNOBSERVABLE`，不写坐标，平面图不标点，告警照常生成。

检测权重不在仓库中。配置示例指向 `models/yolo26s-ft-2026-11-04/best.pt`。火焰阈值 0.30，烟雾阈值 0.35，写在 `config.json`，不在代码里写死。

本机配置是仓库根目录的 `config.json`，示例是 `config.example.json`。`config.json` 不提交。Windows 启动脚本是 `scripts/windows/bootstrap.ps1`、`start-server.ps1`、`start-web.ps1`、`start-streams.ps1` 和 `stop.ps1`。

后端测试是 `python -m pytest apps/server/tests`。前端构建是在 `apps/web` 执行 `npm run build`。

千问分析和阿里云短信都有配置开关。喷水泵保持原有串口协议，监控页可以紧急停泵。

## 训练交付里仍然有效的数字

YOLO26s@640 正式训练和低学习率微调的评测数字来自 2026-11-08 交接，本次没有重新跑评测。交接见 [训练交接](../training/yolo26s-handoff-2026-11-08.md)。

| 同一测试集 | YOLO11s 基线 | YOLO26s 正式 | YOLO26s 微调 |
|---|---:|---:|---:|
| D-Fire mAP50 | 0.745 | 0.733 | 0.731 |
| D-Fire mAP50-95 | 0.432 | 0.428 | 0.419 |
| COCO 背景误报图片数，confidence 0.25 | 39/334 | 10/334 | 6/334 |

微调减少了这组背景图片的误报，D-Fire mAP 同时下降。IFireSmoke 测试集只有 6 张，不能用来说明泛化。在线阈值采用交接建议的火焰 0.30、烟雾 0.35，不是上表里的 0.25。

## 还没有在现场核对的事

控制点、平面图比例和原点需要在教室里测量。四路几何定位的真实误差、MediaMTX 四路延迟，以及水泵是否实际出水，都没有写进这次仓库记录。

## 文档

- 启动和配置字段：[README](../../README.md)
- 训练流程：[YOLO26s v3](../training/yolo26s-v3.md)，协作：[协作规则](../training/collaboration.md)
- 评测文件：[metrics.json](../experiments/2026-11-04-yolo26s/metrics.json)，合成实验：[variable-layout.json](../experiments/2026-11-08-variable-layout.json)
- 几何方案仍是研究记录，不是操作步骤：[四摄研究方案](../plans/后续四摄算法方案-YOLO26s.md)

`docs/plans/` 里的前后端计划和 2026-10-18 联调说明描述的是当时的设想或旧程序，不是现在的启动方法。
