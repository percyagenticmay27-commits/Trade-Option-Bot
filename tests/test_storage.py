from datetime import datetime, timezone

from option_bot.storage import AuditRepository


NOW = datetime(2026, 9, 14, 14, 0, tzinfo=timezone.utc)


def test_append_records_are_idempotent_across_restarts(tmp_path) -> None:
    path = tmp_path / "audit.sqlite3"
    repo = AuditRepository(path)
    first = repo.record_cycle("cycle-1", {"decision": "NO_TRADE"}, "cfg", "model", NOW)
    repo.close()
    reopened = AuditRepository(path)
    second = reopened.record_cycle("cycle-1", {"decision": "NO_TRADE"}, "cfg", "model", NOW)
    assert first == second
    assert reopened.count("cycle") == 1


def test_correction_appends_and_supersedes_original(tmp_path) -> None:
    repo = AuditRepository(tmp_path / "audit.sqlite3")
    original = repo.record_outcome("outcome-1", {"pnl": "10"}, "cfg", "model", NOW)
    corrected = repo.record_outcome("outcome-1-correction", {"pnl": "8"}, "cfg", "model", NOW, supersedes_id=original)
    assert corrected != original and repo.get(corrected)["supersedes_id"] == original
    assert repo.count("outcome") == 2


def test_records_hashes_timestamps_and_complete_delta_ladder(tmp_path) -> None:
    repo = AuditRepository(tmp_path / "audit.sqlite3")
    payload = {"attempts": [{"delta": value, "accepted": False, "reasons": ["NO_CREDIT"]} for value in ("0.08", "0.10", "0.12", "0.15", "0.18", "0.20")]}
    row_id = repo.record_candidate("scan-1", payload, "cfg-hash", "model-hash", NOW)
    row = repo.get(row_id)
    assert row["config_hash"] == "cfg-hash" and row["model_hash"] == "model-hash"
    assert row["source_time"] == NOW.isoformat()
    assert len(row["payload"]["attempts"]) == 6
