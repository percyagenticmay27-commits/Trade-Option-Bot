"""Explicit paper-only operational command surface."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from option_bot.config import ConfigError, OptionBotConfig
from option_bot.providers.http import build_json_transport


COMMANDS = ("health", "scan-once", "manage-once", "close-all-paper", "render-reports")
DATA_BASE_URL = "https://data.alpaca.markets"


def _provider_health(config: OptionBotConfig) -> tuple[str, dict[str, int | str]]:
    paper = build_json_transport(
        config.alpaca_base_url, config.alpaca_key_id, config.alpaca_secret_key
    )
    market = build_json_transport(
        DATA_BASE_URL, config.alpaca_key_id, config.alpaca_secret_key
    )
    checks: dict[str, int | str] = {}
    requests = (
        ("paper_account", paper, "/v2/account", {}),
        ("stock_snapshot", market, "/v2/stocks/snapshots", {"symbols": "AAPL"}),
        (
            "option_snapshot",
            market,
            "/v1beta1/options/snapshots/AAPL",
            {"feed": "indicative", "limit": 1},
        ),
    )
    for name, transport, path, params in requests:
        try:
            status, _ = transport("GET", path, params, None)
            checks[name] = status
        except (OSError, TimeoutError, ValueError, json.JSONDecodeError):
            checks[name] = "UNAVAILABLE"
    ready = all(status == 200 for status in checks.values())
    return ("READY" if ready else "UNAVAILABLE"), checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="option-bot")
    parser.add_argument("command", nargs="?", choices=COMMANDS, default="health")
    parser.add_argument("--fixture-date")
    parser.add_argument("--output-dir", default="results")
    parser.add_argument("--config", default="configs/option-001.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command
    if command == "health":
        try:
            config = OptionBotConfig.load(os.environ, Path(args.config))
            config.database_path.parent.mkdir(parents=True, exist_ok=True)
            writable = os.access(config.database_path.parent, os.W_OK)
            provider_status, provider_checks = _provider_health(config)
            payload = {
                **config.safe_summary(),
                "database_writable": writable,
                "provider_status": provider_status,
                "provider_checks": provider_checks,
            }
            print(json.dumps(payload, sort_keys=True))
            return 0 if writable and provider_status == "READY" else 2
        except (ConfigError, OSError, ValueError) as exc:
            print(json.dumps({"status": "CONFIG_UNAVAILABLE", "paper_only": True, "detail": str(exc)}, sort_keys=True))
            return 2
    if command == "render-reports":
        if not args.fixture_date:
            print("render-reports: --fixture-date is required")
            return 2
        from option_bot.reporting import ReportBuilder
        ReportBuilder(Path(args.output_dir)).build(args.fixture_date)
        print(f"OPTION-001 paper reports rendered to {args.output_dir}")
        return 0
    print(f"{command}: requires configured paper-only runtime")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
