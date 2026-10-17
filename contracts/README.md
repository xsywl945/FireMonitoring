# Shared contracts

This directory is the cross-service source of truth.

- `openapi/fire-monitoring-v1.yaml`: browser-to-Spring REST contract.
- `events/v1/event-envelope.schema.json`: Redis and WebSocket event envelope.
- `events/v1/payloads/`: payload schemas keyed by `eventType`.
- `examples/`: valid examples used by all three applications in tests.

Breaking changes require a new schema version. Additive optional fields remain within the current version.

REST contract revision 2.0.0 removes the manual incident action endpoint and request schema,
and adds automatic suppression status/stop and per-camera stop. The filename and `/api/v1`
URL namespace remain aligned with retained deployed endpoints so login, rooms and history
keep their existing URLs. Clients must remove manual review calls when adopting revision 2.
Redis event schemas are unchanged at 1.0; the new pump serial protocol is `FIRE_PUMP_V1`.

