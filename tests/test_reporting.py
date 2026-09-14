import json

from option_bot.config import REQUIRED_SYMBOLS
from option_bot.reporting import ReportBuilder


def test_report_builder_writes_all_five_paper_only_artifacts(tmp_path) -> None:
    bundle = ReportBuilder(tmp_path).build("2026-09-14")
    expected = {
        "option_001_summary.json", "option_001_leaderboard.json",
        "option_001_positions.json", "option_001_experience.json",
        "option_001_dashboard.html",
    }
    assert expected.issubset({path.name for path in tmp_path.iterdir()})
    assert bundle.summary["paper_only"] is True
    assert [row["symbol"] for row in bundle.leaderboard] == list(REQUIRED_SYMBOLS)
    for name in expected - {"option_001_dashboard.html"}:
        assert json.loads((tmp_path / name).read_text())["paper_only"] is True


def test_missing_facts_are_pending_not_zero(tmp_path) -> None:
    bundle = ReportBuilder(tmp_path).build("2026-09-14")
    assert bundle.summary["best_neutral"] is None
    assert bundle.leaderboard[0]["premium_score"] is None
    assert bundle.leaderboard[0]["status"] == "PENDING"
