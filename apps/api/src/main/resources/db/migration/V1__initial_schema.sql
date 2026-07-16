CREATE TABLE app_users (
    id BIGINT NOT NULL AUTO_INCREMENT,
    username VARCHAR(50) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    password_hash VARCHAR(100) NOT NULL,
    roles VARCHAR(200) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP(6) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uk_app_users_username UNIQUE (username)
);

CREATE TABLE zones (
    id BIGINT NOT NULL AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    scene_type VARCHAR(30) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uk_zones_name UNIQUE (name)
);

CREATE TABLE cameras (
    id BIGINT NOT NULL AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    source_type VARCHAR(30) NOT NULL,
    source_uri VARCHAR(1000),
    stream_key VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL,
    target_fps DECIMAL(5,2) NOT NULL,
    last_seen_at TIMESTAMP(6),
    created_at TIMESTAMP(6) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uk_cameras_stream_key UNIQUE (stream_key)
);

CREATE TABLE zone_camera_bindings (
    id BIGINT NOT NULL AUTO_INCREMENT,
    zone_id BIGINT NOT NULL,
    camera_id BIGINT NOT NULL,
    view_role VARCHAR(20) NOT NULL,
    weight DECIMAL(5,4) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_binding_zone FOREIGN KEY (zone_id) REFERENCES zones (id) ON DELETE CASCADE,
    CONSTRAINT fk_binding_camera FOREIGN KEY (camera_id) REFERENCES cameras (id) ON DELETE CASCADE,
    CONSTRAINT uk_binding_zone_camera UNIQUE (zone_id, camera_id),
    CONSTRAINT uk_binding_zone_role UNIQUE (zone_id, view_role)
);

CREATE TABLE incidents (
    id BIGINT NOT NULL AUTO_INCREMENT,
    zone_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    primary_type VARCHAR(30) NOT NULL,
    started_at TIMESTAMP(6) NOT NULL,
    acknowledged_at TIMESTAMP(6),
    resolved_at TIMESTAMP(6),
    fusion_score DECIMAL(6,5),
    observations_json TEXT,
    semantic_analysis_json TEXT,
    version BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    CONSTRAINT fk_incident_zone FOREIGN KEY (zone_id) REFERENCES zones (id)
);

CREATE TABLE incident_timeline (
    id BIGINT NOT NULL AUTO_INCREMENT,
    incident_id BIGINT NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    note VARCHAR(2000),
    false_alarm_reason VARCHAR(40),
    actor_username VARCHAR(50) NOT NULL,
    occurred_at TIMESTAMP(6) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_timeline_incident FOREIGN KEY (incident_id) REFERENCES incidents (id) ON DELETE CASCADE
);

CREATE TABLE idempotency_records (
    id BIGINT NOT NULL AUTO_INCREMENT,
    idempotency_key VARCHAR(36) NOT NULL,
    incident_id BIGINT NOT NULL,
    request_action VARCHAR(40) NOT NULL,
    request_fingerprint VARCHAR(64) NOT NULL,
    result_status VARCHAR(30) NOT NULL,
    response_json TEXT NOT NULL,
    created_at TIMESTAMP(6) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uk_idempotency_key UNIQUE (idempotency_key),
    CONSTRAINT fk_idempotency_incident FOREIGN KEY (incident_id) REFERENCES incidents (id) ON DELETE CASCADE
);

CREATE INDEX idx_incidents_status ON incidents (status);
CREATE INDEX idx_incidents_started_at ON incidents (started_at);
CREATE INDEX idx_timeline_incident_time ON incident_timeline (incident_id, occurred_at);
