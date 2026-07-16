# 系统架构概览

```mermaid
flowchart LR
    C1["本机/USB 摄像头"] --> F["Windows FFmpeg"]
    C2["网络摄像头"] --> F
    F --> M["MediaMTX\nRTSP / WHEP / HLS / 录像"]
    M --> W["Vue 操作台"]
    M -. "M2 实时取帧" .-> I["Python 推理服务"]
    R["安全 JSONL 回放"] --> I
    I -->|"v1 事件"| RS["Redis Streams"]
    RS --> A["Spring Boot API"]
    A --> DB["MySQL"]
    A -->|"STOMP"| W
    A --> O["MinIO 证据"]
    I -. "M3" .-> V["Qwen3-VL-Plus"]
    A -. "M3" .-> S["阿里云短信"]
```

## 关键边界

- 视频数据走 MediaMTX，告警事件走 Redis/WebSocket，避免把高带宽视频塞入业务消息；
- Python 只发布版本化事件，不直接修改业务数据库；
- Spring 负责鉴权、幂等、状态流转、通知和审计；
- 浏览器只接收短期播放地址，不接收 RTSP 密码、短信密钥或百炼密钥；
- Redis 消费失败保留 pending 记录，数据库提交后才向前端广播。
