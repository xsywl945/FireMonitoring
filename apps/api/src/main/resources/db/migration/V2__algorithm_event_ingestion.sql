ALTER TABLE incidents ADD COLUMN source_event_id VARCHAR(36);
ALTER TABLE incidents ADD COLUMN trace_id VARCHAR(36);
ALTER TABLE incidents ADD COLUMN dedup_key VARCHAR(200);
ALTER TABLE incidents ADD COLUMN confirmed_at TIMESTAMP(6);
ALTER TABLE incidents ADD COLUMN event_source VARCHAR(100);
ALTER TABLE incidents ADD COLUMN model_version VARCHAR(100);
ALTER TABLE incidents ADD COLUMN fusion_mode VARCHAR(30);

CREATE UNIQUE INDEX uk_incidents_source_event_id ON incidents (source_event_id);
