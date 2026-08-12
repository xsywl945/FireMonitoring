# Windows 单摄像头 YOLO 测试说明

本说明用于验证最小实时链路：

`Integrated Camera → DirectShow/OpenCV → best.pt → 单摄 N/M 时序 → 内存事件统计`

这一步不启动 Docker，不写 Redis，不调用短信或多模态 API，也不代表已经完成网页实时画框。当前模型是研究原型，不能替代认证火灾报警器，也不能作为唯一生命安全链路。

## 已固定的环境

- Python：项目隔离环境 `apps/inference/.conda`（Python 3.11）；
- PyTorch：`2.8.0+cu128`；
- TorchVision：`0.23.0+cu128`；
- Ultralytics：`8.4.100`；
- 模型：`data/training-archive/2026-08-12-yolo11s-primary-v2/models/deployment/best.pt`；
- 模型类别：`0=fire`、`1=smoke`；
- 默认设备：本机 RTX 5060 Laptop GPU；
- 默认摄像头：索引 `0`，即集成摄像头。

Clash Verge TUN 只在首次下载依赖时参与系统联网。脚本不会写 `HTTP_PROXY`、代理端口或云端密钥。依赖安装完成后，单摄测试不需要联网。

## 首次安装

在仓库根目录打开 PowerShell：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\setup-local-yolo.ps1
```

脚本只修改项目自己的 Python 隔离环境。它会安装与训练归档一致的 GPU 运行时，并验证 CUDA 张量运算、GPU 名称和模型类别。

## 打开画框预览

确认 Windows 的“相机”、Teams、腾讯会议、浏览器视频通话等程序没有占用摄像头，然后运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\test-single-camera.ps1
```

在预览窗口按 `Q` 或 `Esc` 正常退出。不要为了测试制造真实火焰或烟雾；可使用屏幕上的公开火灾图片/视频做功能演示，真正验收应使用合法、受控的测试素材。

## 常用参数

运行 50 个推理帧后自动退出：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\test-single-camera.ps1 -MaxFrames 50
```

只验证摄像头和 GPU，不打开预览窗口：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\test-single-camera.ps1 -NoPreview -MaxFrames 10
```

使用另一个摄像头索引：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\test-single-camera.ps1 -CameraIndex 1
```

默认单帧检测门槛为 `0.25`，用于保留候选框；现有时序门槛为置信度 `0.45` 且 5 帧中至少 3 帧有效，用于确认事件。不要把这两个门槛混为一个参数。它们仍需在教室和实验室困难负样本集上重新标定。

## 输出解释

正常退出会打印类似结果：

```json
{"framesProcessed": 10, "eventsPublished": 10, "incidentsConfirmed": 0, "stoppedByUser": false}
```

- `framesProcessed`：真正送入 YOLO 的帧数；
- `eventsPublished`：写入当前发布器的事件数。首测发布器是内存，不会进入业务系统；
- `incidentsConfirmed`：单摄时序确认次数；
- `stoppedByUser`：是否由 `Q`、`Esc` 或 `Ctrl+C` 停止。

## 常见问题

- `cannot open camera index 0`：先关闭其他占用摄像头的软件，再重试；
- 黑屏或设备错误：运行 `scripts/windows/list-cameras.ps1` 确认摄像头名称与状态；
- `CUDA is not available`：运行安装脚本的诊断步骤，并确认 Windows 未禁用独显；
- 误报：先记录原始场景，不要立刻降低时序阈值；后续应把该场景加入困难负样本回归集；
- 没有检测框：当前初步模型在跨来源 D-Fire 补充测试上的 mAP50 为 0.774，泛化仍有限；先确认画面清晰、目标尺寸足够，再保留样本用于后续微调。

## 当前边界

当前命令已经验证本地摄像头、GPU、YOLO、单摄时序管线和事件契约。尚未完成的部分包括：网页叠加检测框、MediaMTX RTSP 实时 worker、事件截图/录像、双摄性能验收、短信和云端多模态端到端联调。
