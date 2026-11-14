# 契约

仍在使用的协议说明：

- `pump-serial-v1.md`：主机和 ESP32 水泵之间的串口协议。

告警在进程内用线程传递，浏览器通过 `/api/v1/events` 的 WebSocket 接收。运行中的 HTTP 契约是后端的 `http://127.0.0.1:8080/openapi.json`。
