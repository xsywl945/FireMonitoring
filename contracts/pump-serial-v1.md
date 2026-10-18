# FIRE_PUMP_V1

Persistent USB serial, 115200 baud, 8N1. ASCII lines terminated by LF; optional CR ignored.
ESP32 firmware is the only GPIO owner. Host must complete HELLO before RUN and must not retry an ambiguous RUN.

| Request | Reply | Meaning |
|---|---|---|
| `HELLO` | `READY FIRE_PUMP_V1` | Identify protocol, does not start output |
| `STATUS` | `STATE ON <id>` or `STATE OFF <id>` | Refresh heartbeat and report output; initial ID is `-` |
| `RUN <id> <durationMs>` | `ACK <id> ON` | Accept output, or acknowledge identical already-running ID without extending deadline |
| Repeated RUN for stopped ID | `ACK <id> OFF` | Remain off, never restart this ID |
| `STOP` | `STOPPED` | Immediately disable output, repeatable |

IDs are 32 hexadecimal UUID characters. Duration is decimal 100–30000 ms. Firmware rejects malformed lines, lines over 99 characters, new IDs while busy, and new IDs within 60 seconds of previous start. Errors: `ERR FORMAT`, `ERR DURATION`, `ERR BUSY`, `ERR COOLDOWN`, `ERR TOO_LONG`, `ERR COMMAND`.

The firmware does not emit asynchronous lines. It closes output on timeout or after 3000 ms without STATUS. Host queries every approximately 500 ms. Initial GPIO state is OFF. A device reset clears volatile ID and cooldown; persistent host command claims prevent incident replay across host restart.

Host record statuses: ATTEMPTING (durably claimed before serial write), RUNNING (matching ACK ON), STOPPED (device OFF or STOPPED response), UNKNOWN (ambiguous response or service restart), SKIPPED (policy rejected). GPIO feedback never proves actual water flow. There is no unauthenticated manual RUN HTTP endpoint.

2026-10-18 extension: physical BOOT is GPIO0, active LOW, debounced 30 ms. After normal startup, hold to force output, release to stop, maximum 30000 ms per press. It bypasses automatic-start cooldown and the host heartbeat requirement, while STOP still takes priority and requires a release before another press. RUN while BOOT is held returns `ERR BOOT_HELD`. STATUS reports `STATE ON BOOT` / `STATE OFF BOOT`; no unsolicited button messages are emitted. A press present at setup is blocked until released. Do not hold BOOT during reset, which selects ROM download mode.

The host reports additive `recognitionMode` (`LOCAL_YOLO` or `VLM`) and nullable `activationSource` (`AUTO` or `BOOT`). BOOT takeover makes an interrupted automatic record UNKNOWN/BOOT_OVERRIDE. Host automatic starts are suppressed while BOOT runs and during the subsequent cooldown. A host emergency lock continues to stop output, including BOOT output, until the service is restarted.

Cloud calls are currently disabled by `INFERENCE_VLM_ENABLED=false`. In local mode only validated live fire confirmation with sufficient temporal fire evidence may start the pump; smoke boxes and candidates remain visible but smoke alone cannot start it. Re-enabling the cloud restores the VLM policy. Replay does not construct a hardware controller in either mode.

Internal inference APIs use `X-Control-Token` for `/api/v1/pump` GET and `/api/v1/pump/stop` POST. Business API proxies these with JWT/RBAC. The browser never receives the control token.

Multi-camera reads: `/api/v1/live/cameras` lists session runtimes; `/api/v1/runtime?cameraId=N`, `/api/v1/live/status?cameraId=N`, `/api/v1/live/stream.mjpg?cameraId=N` select one camera. Internal `/api/v1/local-cameras/stop` accepts `{ "cameraId": N }`, or `{}` to stop all. Max two concurrent devices. Each camera has independent pipeline, evidence queue, runtime and frame buffer.
