from pathlib import Path


ROOT = Path(__file__).parents[1]
UNITS = ROOT / "deploy/systemd"


def test_services_run_as_tradebot_with_explicit_paths_and_no_secrets() -> None:
    services = list(UNITS.glob("*.service"))
    assert len(services) == 4
    for path in services:
        text = path.read_text()
        assert "User=tradebot" in text
        assert "WorkingDirectory=/home/tradebot/Trade-Option-Bot" in text
        assert "APCA_API_SECRET_KEY=" not in text
        assert "https://api.alpaca.markets" not in text


def test_operational_services_use_only_explicit_paper_cli_commands() -> None:
    expected = {
        "trade-option-bot-scan.service": "scan-once",
        "trade-option-bot-manage.service": "manage-once",
        "trade-option-bot-close.service": "close-all-paper",
    }
    for name, command in expected.items():
        text = (UNITS / name).read_text()
        assert f"run_option_bot.sh {command}" in text
        assert "flock" in (ROOT / "scripts/run_option_bot.sh").read_text()


def test_timers_delegate_calendar_truth_to_application_and_close_before_1530() -> None:
    timers = list(UNITS.glob("*.timer"))
    assert len(timers) == 3
    assert all("Persistent=false" in path.read_text() for path in timers)
    close = (UNITS / "trade-option-bot-close.timer").read_text()
    assert "15:25:00 America/New_York" in close
    operations = (ROOT / "docs/OPERATIONS.md").read_text()
    assert "exchange calendar" in operations.lower() and "application gates are authoritative" in operations.lower()


def test_dashboard_restarts_safely_and_deployment_is_paper_only() -> None:
    dashboard = (UNITS / "trade-option-bot-dashboard.service").read_text()
    assert "Restart=on-failure" in dashboard
    deployment = (ROOT / "docs/DEPLOYMENT.md").read_text()
    assert "https://paper-api.alpaca.markets" in deployment
    # A root-owned environment file with group tradebot must retain group-read.
    # Mode 600 would make operational services running as tradebot fail closed.
    assert "chmod 640" in deployment and "rollback" in deployment.lower()


def test_script_has_overlap_protection_and_rejects_unknown_commands() -> None:
    script = (ROOT / "scripts/run_option_bot.sh").read_text()
    assert "flock -n" in script and "CONFIG_UNAVAILABLE" in script
    assert "coverage-once|scan-once|manage-once|close-all-paper|render-reports|health" in script
