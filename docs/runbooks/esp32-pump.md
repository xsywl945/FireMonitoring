# 双 UVC + ESP32 自动喷水

本版保留账号登录、权限、教室和摄像头管理。主流程：每路摄像头 YOLO 检测 → 3/5 帧时序候选 → 千问复核 → 覆盖教室内自动启动水泵。无需人工审核。

## 硬件连接

两只 MF-200 UVC 摄像头插入 Windows 主机 USB，分别选择实际设备编号。相同名称的 UVC 设备仍需分别确认编号，重新插拔可能改变顺序。主机请求 MJPEG 1920×1080、30 fps，实际分辨率和帧率取决于摄像头支持；识别默认每路 5 fps，不承诺两路 1080p 每帧都进行 AI 推理。

ESP32 用 CH340 USB 数据线连接主机，摄像头不接 ESP32。普通 ESP32 不负责运行 YOLO 或大模型。板载 0.96 屏的控制芯片、I²C 引脚和地址尚未确认，基础固件不依赖该屏，状态显示在网页与串口。

以下适用于**高电平触发、支持 3.3V 逻辑的直流 MOSFET 模块**。15A 标称值不能证明输入支持 ESP32，按实物模块端子说明连接，不能仅凭外观照接：

| 连接 | 用途 |
|---|---|
| 12V 电源正/负 → MOSFET 电源输入正/负 | 水泵供电 |
| MOSFET 负载输出 → 泵正/负 | 开关水泵；具体端子以模块说明为准 |
| ESP32 GPIO26 → MOSFET 信号输入 | 默认控制脚，高电平开启 |
| ESP32 GND → MOSFET 信号 GND | 非隔离模块须共地 |
| 泵出水口 → 水管 → 喷雾喷头 | 先验证水泵扬程/压力能否驱动喷头 |
| ESP32 USB → Windows | ESP32 供电和串口通信 |

不要将 12V 接 ESP32 GPIO/3.3V，也不要通过杜邦线承载水泵主电流。若 MOSFET 模块没有输入下拉，增加约 10kΩ 下拉，保证 ESP32 上电与复位时关闭。核实模块有感性负载反向钳位保护；没有则按泵/驱动厂商要求增加续流二极管。主电源加匹配导线、端子和保险保护。25W/12V 对应额定约 2.1A，60W 电源在额定功率上有余量，仍须核实启动电流、接线和模块散热。

220V 输入侧按电源厂商规范由具备资质人员接线并封闭，低压调试时避免接触市电侧。此装置用于受控演示；水不能用于带电设备或不适用水的火情。不得在真实火灾或带电设备上用此原型验收。

## 固件

使用 Arduino IDE 的 Espressif ESP32 开发板支持，将 `firmware/esp32_pump/esp32_pump.ino` 烧录到**已确认是经典 ESP32、且引出 GPIO26**的开发板。CH340 是 USB 串口芯片，不代表 ESP32 的具体型号；若为 C3/S3 等板型，请先核实可用 GPIO，修改 `PUMP_PIN`，不要套用经典 ESP32 的引脚。默认高有效；低有效模块需同时修改 `PUMP_ON/PUMP_OFF` 并验证复位输出。

固件不依赖 ArduinoJson 或 OLED 库。使用 `pinMode/digitalWrite` 设置输出，参见 [Espressif GPIO 文档](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/gpio.html)。

- 上电关闭；单次最大 30 秒，默认由主机请求 5 秒。
- 收到 RUN 后按固定截止时间关闭；重复相同 ID 不重新启动，不延长时间。
- 固件最短启动间隔 60 秒；主机可配置更长。
- 运行期间 3 秒未收到 STATUS 心跳自动关闭，主机每约 0.5 秒查询。
- STOP 立即关闭。软件紧急停止还会锁定自动联动，直到推理服务重启。

串口协议（115200、8N1、ASCII、换行分隔，详见 `contracts/pump-serial-v1.md`）可在不接泵时用串口监视器发送 `HELLO`，应返回 `READY FIRE_PUMP_V1`；`STATUS` 返回 `STATE OFF -`。关闭串口监视器，主机才能独占 COM 口。

## 主机配置和启动

将以下配置放到仓库根 `.env`，串口号、教室 ID 必须替换为实际值；不要直接照抄示例 ID：

```dotenv
DASHSCOPE_API_KEY=填写你自己的密钥
INFERENCE_VLM_GATE_ENABLED=true
INFERENCE_VLM_GATE_FAIL_OPEN=false
PUMP_ENABLED=true
PUMP_SERIAL_PORT=COM7
PUMP_ZONE_ID=1
PUMP_DURATION_MS=5000
PUMP_COOLDOWN_SECONDS=60
```

默认示例 `PUMP_ENABLED=false`。配置完成后会自动执行联动，不存在人工审核或手动启动按钮。修改配置后重启推理服务生效。大模型失败/否定/低置信度、超出 30 秒的证据、其他教室、已停止摄像头、冷却期内的事件不会启动。

已有环境仅补串口依赖：

```powershell
.\apps\inference\.conda\python.exe -m pip install -r .\apps\inference\requirements.txt
.\apps\inference\.conda\python.exe -m serial.tools.list_ports -v
powershell -ExecutionPolicy Bypass -File .\scripts\windows\start-demo.ps1 -LiveInference -SelectCameras
```

`-SelectCameras` 会保留现有教室和绑定，并等待网页选择两只 UVC，不会自动占用笔记本内置摄像头。此命令需要原有 MySQL/Redis/MinIO/Docker 环境及本地 `best.pt`。若没有启用推理，单独执行 `scripts/windows/start-inference.ps1`；不要重复启动已经运行的服务。新环境沿用 README 的 bootstrap/setup 步骤。Python 串口读写配置超时并校验回执，参见 [pySerial API](https://pyserial.readthedocs.io/en/stable/pyserial_api.html)。

在“教室与摄像头”添加两只 USB 摄像头并刷新设备。绑定到同一教室（最多两个），或分别绑定不同教室。在每只摄像头的“接入”窗口分别启动；停止一只不会停止另一只。监控页切换摄像头查看各自实时画面。两路是独立识别，任一路成功复核可触发覆盖教室的泵，本版没有要求两路同时确认或进行跨视角融合。

“自动喷水”页显示覆盖教室、串口状态、输出状态以及最近 100 条持久化指令。`RUNNING/STOPPED` 表示控制器确认输出开/关，**不表示实际出水/成功灭火**；没有水流传感器。证据和事件仍在“识别记录”中查看。

指令发送前存入 `apps/inference/runtime/pump.sqlite3`（以启动脚本工作目录为准）。同一事件不会在进程重启后重发；运行中重启的旧记录标为 UNKNOWN，历史记录不能重放。保留此文件，不要在未查明设备状态时删除。回执丢失时不会重发启动指令；停止请求可重复发送。Python 被强制结束时，ESP32 依靠 3 秒心跳看门狗关闭，或达到最大运行时长关闭。

账号角色：所有已登录用户可读状态，ADMIN/OPERATOR 才能紧急停止。紧急停止无确认弹窗，点击立即发送并锁定；停止确认失败时请检查现场、切断泵的 12V 电源，不能仅依赖页面。

## 验收顺序

1. 泵断电，烧录后确认 GPIO 上电关闭；串口 HELLO/STATUS 正确。
2. 水泵与喷头离开电子设备，在受控容器中验证供水、负载极性、压力以及 5 秒关闭。避免空转；回流泵是否允许空转须按厂商说明。
3. 用测试替身验证 AI 正向判断→单次指令，负向/超时/低置信度不启动。屏幕上的火焰图片可能被大模型正确判为屏幕内容而拒绝，不应为演示降低门控。
4. 两只 UVC 同时运行，确认画面、教室、编号不串线；两个视角近同时确认时仅一条 RUN，另一条显示冷却期跳过。
5. 运行中停止摄像头，等待中的大模型结果不得新启动泵；已开启的泵按原定时间关闭，需立即关闭时使用紧急停止。
6. 点击紧急停止，验证输出关闭且后续事件不启动；断开 USB，验证心跳超时关闭；确认现场后再重启服务恢复。

自动测试可覆盖软件和协议，但无法检验实际 CH340 驱动、USB 带宽、水泵压力、接线和出水。
