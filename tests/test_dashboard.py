from option_bot.config import REQUIRED_SYMBOLS
from option_bot.dashboard import DashboardRenderer
from option_bot.reporting import ReportBuilder


def test_dashboard_contains_required_executive_sections_and_all_symbols(tmp_path) -> None:
    bundle = ReportBuilder(tmp_path).build("2026-09-14", render=False)
    html = DashboardRenderer().render(bundle)
    for text in (
        "PAPER TRADING ONLY", "Market session", "Best neutral setup",
        "Best directional setup", "Selected trades", "Open positions",
        "Completed trades", "Experience Learner", "Rejected candidates",
        "System health", "Evidence details",
    ):
        assert text in html
    for symbol in REQUIRED_SYMBOLS:
        assert f">{symbol}<" in html


def test_dashboard_is_accessible_responsive_and_honest(tmp_path) -> None:
    html = DashboardRenderer().render(ReportBuilder(tmp_path).build("2026-09-14", render=False))
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in html
    assert '<th scope="col">Symbol</th>' in html
    assert "Not available" in html and "data-evidence-id=" in html
    assert "aria-label=\"Filter symbols\"" in html
    assert "https://" not in html


def test_dynamic_text_is_escaped(tmp_path) -> None:
    bundle = ReportBuilder(tmp_path).build("2026-09-14", render=False)
    bundle.leaderboard[0]["reason"] = "<script>alert(1)</script>"
    html = DashboardRenderer().render(bundle)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
