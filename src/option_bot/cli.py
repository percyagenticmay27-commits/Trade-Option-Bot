"""Explicit paper-only operational command surface."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

from option_bot.config import ConfigError, OptionBotConfig
from option_bot.coverage import build_coverage_report
from option_bot.event_intelligence import AlphaVantageNewsSource, RssNewsSource, build_event_intelligence_report
from option_bot.providers.http import PublicHttpClient, build_json_transport


COMMANDS = ("health", "coverage-once", "events-once", "scan-once", "manage-once", "close-all-paper", "render-reports")
DATA_BASE_URL = "https://data.alpaca.markets"
ET = ZoneInfo("America/New_York")


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
    parser.add_argument("--trade-date")
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
    if command == "coverage-once":
        try:
            config = OptionBotConfig.load(os.environ, Path(args.config))
            trade_date = args.trade_date or datetime.now(ET).date().isoformat()
            paper = build_json_transport(
                config.alpaca_base_url, config.alpaca_key_id, config.alpaca_secret_key
            )
            market = build_json_transport(
                DATA_BASE_URL, config.alpaca_key_id, config.alpaca_secret_key
            )
            report = build_coverage_report(
                symbols=config.symbols,
                trade_date=trade_date,
                paper_transport=paper,
                market_transport=market,
            )
            output = Path(args.output_dir) / "option_001_coverage.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(f"OPTION-001 coverage written for {len(config.symbols)} governed symbols: {output}")
            return 0
        except (ConfigError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(json.dumps({"status": "DATA_UNAVAILABLE", "paper_only": True, "detail": str(exc)}, sort_keys=True))
            return 2
    if command == "events-once":
        try:
            config = OptionBotConfig.load(os.environ, Path(args.config))
            alpha_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
            if not alpha_key:
                raise ConfigError("ALPHA_VANTAGE_API_KEY is required for event intelligence")
            client = PublicHttpClient()
            sources = (
                AlphaVantageNewsSource(alpha_key, client.get_json),
                RssNewsSource(
                    "YAHOO_FINANCE",
                    lambda symbol: f"https://finance.yahoo.com/rss/headline?s={quote_plus(symbol)}",
                    client.get_bytes,
                ),
                RssNewsSource(
                    "GOOGLE_NEWS",
                    lambda symbol: (
                        "https://news.google.com/rss/search?"
                        f"q={quote_plus(symbol + ' stock')}&hl=en-US&gl=US&ceid=US:en"
                    ),
                    client.get_bytes,
                ),
            )
            report = build_event_intelligence_report(
                symbols=config.symbols, sources=sources, retrieved_at=datetime.now(ET)
            )
            output = Path(args.output_dir) / "option_001_events.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(f"OPTION-001 event intelligence written for {len(config.symbols)} governed symbols: {output}")
            return 0
        except (ConfigError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(json.dumps({"status": "DATA_UNAVAILABLE", "paper_only": True, "detail": str(exc)}, sort_keys=True))
            return 2
    print(f"{command}: requires configured paper-only runtime")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
