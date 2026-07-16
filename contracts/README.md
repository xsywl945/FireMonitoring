# Shared contracts

This directory is the cross-service source of truth.

- `openapi/fire-monitoring-v1.yaml`: browser-to-Spring REST contract.
- `events/v1/event-envelope.schema.json`: Redis and WebSocket event envelope.
- `events/v1/payloads/`: payload schemas keyed by `eventType`.
- `examples/`: valid examples used by all three applications in tests.

Breaking changes require a new schema version. Additive optional fields remain within the current version.

