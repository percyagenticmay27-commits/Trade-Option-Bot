import json
from pathlib import Path

from option_bot.cli import main


CONFIG = Path(__file__).parents[1] / "configs" / "option-001.json"


def environment() -> dict[str, str]:
    return {
        "APCA_API_KEY_ID": "paper-key",
        "APCA_API_SECRET_KEY": "paper-secret",
        "APCA_API_BASE_URL": "https://paper-api.alpaca.markets",
        "OPTION_BOT_TIMEZONE": "America/New_York",
    }


def test_health_checks_only_read_endpoints_and_reports_ready(monkeypatch, capsys) -> None:
    calls: list[tuple[str, str]] = []

    def transport(base_url, key_id, secret_key):
        assert key_id == "paper-key" and secret_key == "paper-secret"

        def request(method, path, params, body):
            calls.append((method, f"{base_url}{path}"))
            assert body is None
            return 200, {"ok": True}

        return request

    monkeypatch.setattr("option_bot.cli.os.environ", environment())
    monkeypatch.setattr("option_bot.cli.build_json_transport", transport)

    assert main(["health", "--config", str(CONFIG)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["provider_status"] == "READY"
    assert payload["provider_checks"] == {
        "option_snapshot": 200,
        "paper_account": 200,
        "stock_snapshot": 200,
    }
    assert calls == [
        ("GET", "https://paper-api.alpaca.markets/v2/account"),
        ("GET", "https://data.alpaca.markets/v2/stocks/snapshots"),
        ("GET", "https://data.alpaca.markets/v1beta1/options/snapshots/AAPL"),
    ]


def test_health_fails_closed_when_any_provider_check_is_unauthorized(
    monkeypatch, capsys
) -> None:
    def transport(base_url, *_):
        def request(method, path, params, body):
            return (401, {"message": "unauthorized"}) if "options" in path else (200, {})

        return request

    monkeypatch.setattr("option_bot.cli.os.environ", environment())
    monkeypatch.setattr("option_bot.cli.build_json_transport", transport)

    assert main(["health", "--config", str(CONFIG)]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["provider_status"] == "UNAVAILABLE"
    assert payload["provider_checks"]["option_snapshot"] == 401
    assert "paper-key" not in json.dumps(payload)
    assert "paper-secret" not in json.dumps(payload)


def test_coverage_once_writes_governed_read_only_report(monkeypatch, tmp_path, capsys) -> None:
    def transport(base_url, *_):
        def request(method, path, params, body):
            if path == "/v2/options/contracts":
                symbol = params["underlying_symbols"]
                return 200, {"option_contracts": [{
                    "symbol": f"{symbol}260914P00100000",
                    "style": "american",
                    "settlement_type": "physical",
                }]}
            return 200, {"snapshots": {}}
        return request

    monkeypatch.setattr("option_bot.cli.os.environ", environment())
    monkeypatch.setattr("option_bot.cli.build_json_transport", transport)

    assert main([
        "coverage-once", "--config", str(CONFIG), "--trade-date", "2026-09-14",
        "--output-dir", str(tmp_path),
    ]) == 0
    payload = json.loads((tmp_path / "option_001_coverage.json").read_text())
    assert len(payload["symbols"]) == 12
    assert payload["order_submission_enabled"] is False
    assert "12 governed symbols" in capsys.readouterr().out
