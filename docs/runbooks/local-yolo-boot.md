# 本地火灾识别喷水与 BOOT 按钮

2026-10-18 当前模式：本地 YOLO → 火焰 3/5 帧时序确认 → 自动喷水 5 秒。大模型接口暂时关闭，即使已保存密钥也不会调用。烟雾仅展示检测框和候选提示，不因烟雾单独喷水；更强的烟雾分数不会遮蔽已经确认的火焰。

## 使用

- ESP32 上层 USB Type-C 保持连接电脑，CH340 当前为 COM14。
- 开发板正常启动后，按住 BOOT 强制喷水，松开停止；单次最多 30 秒，超时必须松开后再次按下。不要在上电或按 EN 时一直按 BOOT，否则会进入下载模式。
- 自动喷水每次 5 秒，冷却 60 秒。BOOT 可绕过自动启动冷却，不需要主机心跳；网页紧急停止锁定仍具有更高优先级。
- 单摄：在“教室与摄像头”仅启动一只真实摄像头。
- 双摄：接上第二只真实 UVC，刷新设备列表，选择正确编号并分别启动。两路独立识别，共用一只泵和冷却时间，不要求同时检出。
- 水泵仅覆盖 `PUMP_ZONE_ID` 配置的教室。设备拔插会改变编号，不能照抄旧编号。

目前用户只接入一只 USB Camera，已设现有摄像头 ID 2 为设备编号 0、保留教室 ID 2 绑定。第二路 ID 3 保留但未启动；接入第二只后再选设备编号。不要选择内置或虚拟摄像头冒充第二只 UVC。

## 当前本机配置

根 `.env` 中以下键已应用，已有密钥和账号数据保留：

```dotenv
INFERENCE_VLM_ENABLED=false
INFERENCE_VLM_GATE_ENABLED=false
INFERENCE_VLM_GATE_FAIL_OPEN=false
PUMP_ENABLED=true
PUMP_SERIAL_PORT=COM14
PUMP_ZONE_ID=2
PUMP_DURATION_MS=5000
PUMP_COOLDOWN_SECONDS=60
```

恢复大模型时，设置 `INFERENCE_VLM_ENABLED=true` 和 `INFERENCE_VLM_GATE_ENABLED=true` 并重启推理服务。没有必要删除或重填已保存的密钥。

## 固件与验证

正常固件工程为 `firmware/esp32_pump`，已修复 `.ino.cpp` 生成文件的 PlatformIO 源过滤配置，使用 Espressif 32 7.1.3。不要再烧录 `firmware/pump_power_on_test`；该旧接线测试会持续开启输出。

本次真实 ESP32 烧录写入校验通过，串口 HELLO 和连续三次 STATUS OFF 通过。BOOT 按住/释放、最大运行时间、STOP 优先、上电已按住不启动等行为由固件主机测试覆盖，实际按键和实际出水仍需现场观察；没有水流传感器，不能把 GPIO 回执当作出水证明。

软件验证：Python 全量 48 项通过，前端 7 项通过，ruff/ESLint/TypeScript/Vite 构建通过；固件主机协议测试和真实 ESP32 目标编译通过。48 项包含关闭云端仍可联动、BOOT 接管状态、仅烟雾不喷水和更强烟雾不遮蔽后续火焰的回归测试。

推理服务已重启并确认大模型开关为关闭。相机启动自动操作被系统审批拒绝（仅返回 blocked by policy），最终保持摄像头待启动，由用户在网页点击“启动识别”。此前枚举已确认只有一只真实 USB 摄像头，不能声称本次通过双 UVC 实机验收。

确认供水、喷头朝向容器并远离电子设备后再接通 12V 做短时试验。识别测试使用已有样本/受控回放，不制造真实火灾。根目录 Windows 启动入口仍为 `scripts/windows/start-demo.ps1 -LiveInference -SelectCameras`，已运行的服务不必重复启动。
