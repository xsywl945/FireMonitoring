# 契约

- `actuator-serial-v2.md`：执行节点，水泵、舵机、激光和急停。
- `panel-serial-v2.md`：报警节点，三色灯、蜂鸣和屏幕。
- 接线见 `docs/hardware/wiring.md`。

告警在进程内用线程传递。浏览器通过 `/api/v1/events` 接收 WebSocket。HTTP 契约是后端运行时的 `http://127.0.0.1:8080/openapi.json`。
