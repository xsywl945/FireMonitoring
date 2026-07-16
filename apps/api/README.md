# Fire Monitoring Business API

Spring Boot 3 / Java 17 business-control API for the intelligent fire-monitoring prototype. The implementation follows `contracts/openapi/fire-monitoring-v1.yaml` and intentionally keeps camera capture and YOLO inference outside this process.

## Implemented MVP

- stateless JWT login and seeded demo administrator;
- role-protected zone/camera mutation and authenticated read APIs;
- one/two-camera zone bindings with duplicate-camera/view validation;
- source URI masking, configuration-only probe stub, and short-lived MediaMTX URLs;
- dashboard summary;
- incident queries, detail timeline, strict state transitions, optimistic locking, and UUID idempotency keys;
- consistent JSON errors with `X-Trace-Id`;
- STOMP endpoint at `/ws/events` and incident updates on `/topic/incidents` (send the JWT in the STOMP `CONNECT` `Authorization` header);
- Flyway migrations for MySQL and H2-backed integration tests;
- public liveness/readiness endpoint at `/actuator/health`.

The camera probe is explicitly an MVP configuration probe. It does not open DirectShow or RTSP; the native ingest controller / MediaMTX health integration will replace it in the media phase.

## Run locally

Requirements: Java 17, Maven 3.9+, and MySQL 8.

Create a database and set environment variables before starting:

```powershell
$env:DB_URL = 'jdbc:mysql://localhost:3306/fire_monitoring?useUnicode=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai&allowPublicKeyRetrieval=true&useSSL=false'
$env:DB_USERNAME = 'fire_monitoring'
$env:DB_PASSWORD = '<local database password>'
$env:JWT_SECRET = '<random secret of at least 32 bytes>'
$env:DEMO_ADMIN_PASSWORD = '<strong local demo password>'
mvn spring-boot:run
```

For the current project defaults, the API listens on `http://localhost:8080`. Login is `POST /api/v1/auth/login`. The development-only seeded username is `admin`; when `DEMO_ADMIN_PASSWORD` is not set its fallback is `FireAdmin123!`. Never use that fallback outside an isolated local demo.

## Test and package

```powershell
mvn test
mvn clean package
```

Tests use an isolated in-memory H2 database in MySQL compatibility mode. They verify login/authentication, error envelopes, validation, zone/camera binding and RTSP masking, stream ticket generation, incident state transitions, false-alarm validation, and idempotent retries.

## Runtime configuration

| Variable | Default | Purpose |
|---|---|---|
| `DB_URL` | local MySQL `fire_monitoring` | JDBC connection |
| `DB_USERNAME` / `DB_PASSWORD` | development values | database credentials |
| `JWT_SECRET` | development-only value | HMAC signing key, minimum 32 bytes |
| `JWT_EXPIRATION_SECONDS` | `3600` | access-token lifetime |
| `CORS_ALLOWED_ORIGINS` | localhost Vite/Nginx origins | comma-separated exact origins |
| `MEDIA_WHEP_BASE_URL` | `http://localhost:8889` | MediaMTX WHEP base URL |
| `MEDIA_HLS_BASE_URL` | `http://localhost:8888` | MediaMTX HLS base URL |
| `MEDIA_TICKET_TTL_SECONDS` | `120` | URL response expiration marker |
| `DEMO_ADMIN_*` | local demo values | one-time seeded admin identity |

`sourceUri` is currently stored in MySQL so the future ingest controller can consume it. API responses and normal logs never return it unmasked. Production hardening should encrypt this column or move camera credentials to a secrets manager before any non-local deployment.
