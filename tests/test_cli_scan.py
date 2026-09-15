import json

from option_bot.cli import main


def test_scan_once_writes_current_paper_only_reports(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APCA_API_KEY_ID", "test-key")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "test-secret")
    monkeypatch.setenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")
    monkeypatch.setenv("OPTION_BOT_TIMEZONE", "America/New_York")
    monkeypatch.setenv("OPTION_BOT_DB_PATH", str(tmp_path / "audit.sqlite3"))

    result = main([
        "scan-once",
        "--trade-date", "2026-09-15",
        "--output-dir", str(tmp_path),
        "--config", "configs/option-001.json",
    ])

    assert result == 0
    summary = json.loads((tmp_path / "option_001_summary.json").read_text())
    leaderboard = json.loads((tmp_path / "option_001_leaderboard.json").read_text())
    assert summary["trade_date"] == "2026-09-15"
    assert summary["paper_only"] is True
    assert summary["order_submission_enabled"] is False
    assert len(leaderboard["leaderboard"]) == 12
