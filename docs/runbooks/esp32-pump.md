# ESP32 自动喷水

账号、教室、摄像头和告警在 FastAPI 服务里。教室最多绑定 4 路，画面走 MediaMTX。泵仍由主机串口按原协议控制，参数在 `config.json` 的 `pump`。启动见 [README](../../README.md)。

## 硬件连接

USB 摄像头插入 Windows 主机。相同名称的设备要分别确认 DirectShow 名称，重新插拔后名称可能变化。推流帧率用摄像头自己的 `target_fps`，不承诺每一帧都做检测。

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

### VS Code + PlatformIO IDE

项目已包含 `firmware/esp32_pump/platformio.ini`，无需另建工程或复制代码。
在 PlatformIO Home 选择 **Open Project**，打开 `firmware/esp32_pump` 文件夹。
配置为 Espressif ESP32 Dev Module (`esp32dev`) + Arduino，适用于经典 ESP32/ESP32-WROOM DevKitC。
若模块标识含 C3/S3/S2，请先重新确认型号，不能直接使用该配置。
参考 [PlatformIO 的 DevKitC 入门说明](https://docs.platformio.org/en/latest/tutorials/espressif32/arduino_debugging_unit_testing.html)。

30P Expansion Board 是扩展底板，不作为 PlatformIO 的开发板型号；它是否适配 DevKitC 取决于实物两侧针数、针距与引脚顺序，不能仅凭商品名称保证。请确认后再插入。

先不接 MOSFET 和水泵，只用 USB 数据线连接 ESP32。等待首次工具链安装完成，按 **Build** 编译，再按 **Upload** 烧录。多串口时，在 `platformio.ini` 增加 `upload_port = COM实际编号` 和 `monitor_port = COM实际编号`；COM 号需在设备管理器中确认。
打开 **Serial Monitor**（115200），发送带换行的 `HELLO`，应收到 `READY FIRE_PUMP_V1`；发送 `STATUS` 应看到 `STATE OFF -`。完成后关闭监视器，再由 Python 服务独占串口。

### Arduino IDE（备选）

使用 Arduino IDE 的 Espressif ESP32 开发板支持，将 `firmware/esp32_pump/esp32_pump.ino` 烧录到**已确认是经典 ESP32、且引出 GPIO26**的开发板。CH340 是 USB 串口芯片，不代表 ESP32 的具体型号；若为 C3/S3 等板型，请先核实可用 GPIO，修改 `PUMP_PIN`，不要套用经典 ESP32 的引脚。默认高有效；低有效模块需同时修改 `PUMP_ON/PUMP_OFF` 并验证复位输出。

固件不依赖 ArduinoJson 或 OLED 库。使用 `pinMode/digitalWrite` 设置输出，参见 [Espressif GPIO 文档](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/gpio.html)。

- 上电关闭；单次最大 30 秒，默认由主机请求 5 秒。
- 收到 RUN 后按固定截止时间关闭；重复相同 ID 不重新启动，不延长时间。
- 固件最短启动间隔 60 秒；主机可配置更长。
- 运行期间 3 秒未收到 STATUS 心跳自动关闭，主机每约 0.5 秒查询。
- STOP 立即关闭。软件紧急停止还会锁定自动联动，直到推理服务重启。

串口协议（115200、8N1、ASCII、换行分隔，详见 `contracts/pump-serial-v1.md`）可在不接泵时用串口监视器发送 `HELLO`，应返回 `READY FIRE_PUMP_V1`；`STATUS` 返回 `STATE OFF -`。关闭串口监视器，主机才能独占 COM 口。

## 主机配置和启动

串口、教室 id、时长和冷却写在 `config.json` 的 `pump`。`enabled` 为 true 时必须填写 `serial_port` 和 `zone_id`。`zone_id` 是教室 id。示例里的泵默认关闭。改完配置后重启后端。

列出本机串口：

```powershell
python -m serial.tools.list_ports -v
```

Python 串口读写的超时说明见 [pySerial API](https://pyserial.readthedocs.io/en/stable/pyserial_api.html)。

在教室里绑定摄像头，最多 4 路。监控页是四宫格。登录后可以在实时监控页紧急停泵。`RUNNING` 或 `STOPPED` 只表示控制器回执，不表示实际出水。没有水流传感器。

命令记录文件由 `pump.journal_path` 指定，示例是 `runtime/pump.sqlite3`。同一事件不会在进程重启后重发。回执丢失时不会重发启动指令。停止请求可以重复发送。Python 进程被强制结束后，ESP32 靠心跳超时或最大运行时长关闭输出。紧急停止失败时切断泵的 12V 电源，不能只看页面。

## 验收顺序

1. 泵断电，烧录后确认 GPIO 上电关闭；串口 HELLO/STATUS 正确。
2. 水泵与喷头离开电子设备，在受控容器中验证供水、负载极性、压力以及 5 秒关闭。避免空转；回流泵是否允许空转须按厂商说明。
3. 用测试替身验证 AI 正向判断→单次指令，负向/超时/低置信度不启动。屏幕上的火焰图片可能被大模型正确判为屏幕内容而拒绝，不应为演示降低门控。
4. 多路摄像头同时运行时，确认画面和教室没有串线。冷却期内的另一次确认不会再发 RUN。
5. 运行中停止摄像头，等待中的大模型结果不得新启动泵；已开启的泵按原定时间关闭，需立即关闭时使用紧急停止。
6. 点击紧急停止，验证输出关闭且后续事件不启动；断开 USB，验证心跳超时关闭；确认现场后再重启服务恢复。

自动测试可覆盖软件和协议，但无法检验实际 CH340 驱动、USB 带宽、水泵压力、接线和出水。
