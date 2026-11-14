# FIRE_ACTUATOR_V2

执行节点（ESP32-A）与主机之间的串口协议。115200 波特，8N1，一行一条命令，以 LF 结束，CR 忽略。固件不主动发报文。上电时水泵和激光关闭，舵机在 0°。

| 主机发送 | 回复 | 含义 |
|---|---|---|
| `HELLO` | `READY FIRE_ACTUATOR_V2` | 识别固件，不启动输出 |
| `PING` | `PONG` | 心跳 |
| `STATUS` | `STATE <泵> <激光> <锁> <水平百分度> <俯仰百分度>` | 泵和激光是 `ON` 或 `OFF`。锁是 `CLEAR`、`LATCHED` 或 `ARMED`。角度是当前有符号百分度 |
| `RUN <id> <毫秒>` | `ACK <id> ON` | 开泵。`id` 是 32 位十六进制。时长 100–30000 |
| 同一 `id` 再次 `RUN` | `ACK <id> ON` 或 `ACK <id> OFF` | 正在喷时不延长；已经结束则保持关闭 |
| 喷水中换一个 `id` | `ERR BUSY` | 拒绝 |
| `STOP` | `STOPPED` | 立刻关泵、关激光，不解除急停锁存 |
| `AIM <水平> <俯仰>` | `AIM <水平> <俯仰>` | 目标百分度。水平 −12000…12000，俯仰 0…6000。实际转动不超过 90°/s |
| `LASER ON` / `LASER OFF` | 同样的一行 | 激光。急停锁存时拒绝 |
| `UNLOCK` | `UNLOCKED` | 急停已松开且复位键已按下之后，解除锁存 |

错误行：`ERR FORMAT`、`ERR DURATION`、`ERR BUSY`、`ERR ESTOP`、`ERR RESET`、`ERR LIMIT`、`ERR TOO_LONG`、`ERR COMMAND`。超过 99 个字符的一行是 `ERR TOO_LONG`。

急停常开触点按下后固件锁存：关泵、关激光、停止舵机脉宽。此后 `RUN`、`AIM`、`LASER` 都回 `ERR ESTOP`。只松急停不够。复位键按下后状态变成 `ARMED`，主机再发 `UNLOCK` 才恢复。急停仍按着时 `UNLOCK` 回 `ERR ESTOP`；还没按复位键时回 `ERR RESET`。

任意合法命令都刷新心跳。泵或激光开着时，3000 ms 没有主机命令就关泵、关激光，舵机停在当前角度。单次喷水最长 30 s。

舵机是 50 Hz PWM。0 百分度对应 1500 µs，按 TBS-K20 的 500–2500 µs / 270° 换算。超出软件限位的 `AIM` 回 `ERR LIMIT`，角度不变。

GPIO 不证明出了水。主机在收到明确的 `ACK <id> ON` 之前不得把这次 `RUN` 当成成功；超时按不确定处理，不得用同一个 `id` 再发一次。
