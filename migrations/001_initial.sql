PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS audit_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_type TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    model_hash TEXT NOT NULL,
    source_time TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    supersedes_id INTEGER REFERENCES audit_records(id),
    UNIQUE(record_type, idempotency_key)
);

CREATE INDEX IF NOT EXISTS ix_audit_records_type_time
ON audit_records(record_type, recorded_at);
