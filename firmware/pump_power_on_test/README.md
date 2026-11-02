# GPIO26 上电启动水泵接线测试

独立的 PlatformIO 工程，用于 ESP32-WROOM-32 和高电平触发、支持 3.3V 输入的 MOSFET。

- ESP32 GPIO26 / D26 信号端 → MOSFET IO。
- ESP32 GND → MOSFET 控制 GND。
- ESP32 上层开发板 USB Type-C → 电脑。
- MOSFET 电源输入、泵负载输出按模块标识接线；先核实 12V 直流正负极。

固件进入 `setup()` 后将 GPIO26 持续置为 HIGH。ESP32 芯片启动前的引脚状态不由此程序控制，因此这里的“上电启动”指固件启动后开启。

**没有定时停止、心跳看门狗或串口 STOP 功能。断开水泵 12V 电源才能可靠停止水泵。**
这是接线测试，不能用作正式自动灭火固件。串口文字只报告软件输出意图，不证明负载电压、电机运行或实际出水。

## 使用

1. 保持水泵 12V 电源断开。在 VS Code / PlatformIO 中打开本文件夹。
2. Build，确认实际 CH340 串口后 Upload。不要把蓝牙串口作为烧录端口。
3. 确认泵有正常供水、出水朝向容器且电子设备远离水，核实电源极性与接线后再接通泵的 12V 电源。此时泵应立即启动（前提是 MOSFET 高有效且兼容 3.3V）。
4. 短时间观察后断开 12V，避免空转或持续喷水。
5. 测试完成后烧回相邻 `../esp32_pump/` 工程。正常固件为上电关闭，必须经协议指令才开启，并有超时和心跳保护。

命令行示例（端口以实际检测为准）：

```powershell
pio run -d firmware/pump_power_on_test
pio run -d firmware/pump_power_on_test -t upload --upload-port COM实际编号
```

串口波特率 115200；持续输出 `PUMP_POWER_ON_TEST` 标识用于区分正式固件。

## 2026-10-18 实机记录

- PlatformIO Core 6.2.0，Espressif 32 平台 7.1.3；ESP32 目标编译成功。
- CH340 串口实际枚举为 COM14；烧录识别芯片 ESP32-D0WDQ6 revision v1.1。
- 已完成真实烧录，Flash 写入校验通过，随后自动复位。
- 实际收到 `PUMP_POWER_ON_TEST: GPIO26=HIGH; continuous output enabled.` 及循环状态输出；串口读取过程未发送启动命令。
- 用户在烧录前确认水泵 12V 已断开。没有测量 GPIO 电压、验证 MOSFET 开通或观察实际水泵/出水，不能将串口回包等同于实际出水成功。
- 本工程已设置当前 COM14；重新插拔如改变端口，请修改 `platformio.ini` 的 `upload_port` 和 `monitor_port`。
