"""Transactional append-oriented SQLite audit ledger."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class AuditRepository:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        migration = Path(__file__).parents[2] / "migrations" / "001_initial.sql"
        self._connection.executescript(migration.read_text(encoding="utf-8"))

    def close(self) -> None:
        self._connection.close()

    def _record(self, record_type: str, key: str, payload: Mapping[str, Any], config_hash: str, model_hash: str, source_time: datetime, supersedes_id: int | None = None) -> int:
        if source_time.tzinfo is None:
            raise ValueError("source_time must be timezone-aware")
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        recorded_at = datetime.now(timezone.utc).isoformat()
        with self._connection:
            existing = self._connection.execute("SELECT id FROM audit_records WHERE record_type=? AND idempotency_key=?", (record_type, key)).fetchone()
            if existing:
                return int(existing["id"])
            cursor = self._connection.execute(
                "INSERT INTO audit_records(record_type,idempotency_key,payload_json,config_hash,model_hash,source_time,recorded_at,supersedes_id) VALUES(?,?,?,?,?,?,?,?)",
                (record_type, key, canonical, config_hash, model_hash, source_time.isoformat(), recorded_at, supersedes_id),
            )
            return int(cursor.lastrowid)

    def get(self, row_id: int) -> dict[str, Any]:
        row = self._connection.execute("SELECT * FROM audit_records WHERE id=?", (row_id,)).fetchone()
        if row is None:
            raise KeyError(row_id)
        result = dict(row)
        result["payload"] = json.loads(result.pop("payload_json"))
        return result

    def count(self, record_type: str) -> int:
        return int(self._connection.execute("SELECT COUNT(*) FROM audit_records WHERE record_type=?", (record_type,)).fetchone()[0])

    def find(self, record_type: str, key: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT id FROM audit_records WHERE record_type=? AND idempotency_key=?",
            (record_type, key),
        ).fetchone()
        return self.get(int(row["id"])) if row else None

    def record_cycle(self, key, payload, config_hash, model_hash, source_time, supersedes_id=None):
        return self._record("cycle", key, payload, config_hash, model_hash, source_time, supersedes_id)

    def record_evidence(self, key, payload, config_hash, model_hash, source_time, supersedes_id=None):
        return self._record("evidence", key, payload, config_hash, model_hash, source_time, supersedes_id)

    def record_candidate(self, key, payload, config_hash, model_hash, source_time, supersedes_id=None):
        return self._record("candidate", key, payload, config_hash, model_hash, source_time, supersedes_id)

    def record_order(self, key, payload, config_hash, model_hash, source_time, supersedes_id=None):
        return self._record("order", key, payload, config_hash, model_hash, source_time, supersedes_id)

    def record_fill(self, key, payload, config_hash, model_hash, source_time, supersedes_id=None):
        return self._record("fill", key, payload, config_hash, model_hash, source_time, supersedes_id)

    def record_position_event(self, key, payload, config_hash, model_hash, source_time, supersedes_id=None):
        return self._record("position_event", key, payload, config_hash, model_hash, source_time, supersedes_id)

    def record_outcome(self, key, payload, config_hash, model_hash, source_time, supersedes_id=None):
        return self._record("outcome", key, payload, config_hash, model_hash, source_time, supersedes_id)
