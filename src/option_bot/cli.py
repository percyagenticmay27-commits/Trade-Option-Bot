"""Explicit paper-only operational command surface."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

from option_bot.scheduled_events import apply_scheduled_event_policy
from option_bot.daily_events import daily_event_report, _write as write_event_json
from option_bot.config import ConfigError, OptionBotConfig
from option_bot.domain import Money, PaperMultiLegOrder
from option_bot.coverage import build_coverage_report
from option_bot.evidence import EvidenceEngine
from option_bot.event_intelligence import (
    RssNewsSource,
    build_event_intelligence_report,
    canonical_news_query,
)
from option_bot.live_scan import EvaluatedSetup, build_scan_report, evaluate_live_scan
from option_bot.providers.http import PublicHttpClient, build_json_transport
from option_bot.providers.robinhood_research import (
    load_robinhood_research_bars,
    load_robinhood_research_surface,
)
from option_bot.research_gate import validate_research_snapshot
from option_bot.local_paper import LocalPaperSimulation
from option_bot.refresh_queue import request_refresh, complete_refresh
from option_bot.live_scan import refresh_paper_reports
from option_bot.scheduled_events import (
    BEA_URL,
    BLS_URL,
    FED_URL,
    OfficialCalendarSource,
    parse_bea_schedule,
    parse_bls_ics,
    parse_fomc_calendar,
    parse_fed_chair_calendar,
    fed_chair_calendar_url,
)


COMMANDS = ("health", "coverage-once", "events-once", "scan-once", "manage-once", "close-all-paper", "render-reports")
DATA_BASE_URL = "https://data.alpaca.markets"
ET = ZoneInfo("America/New_York")


def _event_report(config: OptionBotConfig, retrieved_at: datetime) -> dict:
    client = PublicHttpClient()
    return build_event_intelligence_report(
        symbols=config.symbols,
        sources=(
            RssNewsSource(
                "YAHOO_FINANCE",
                lambda symbol: f"https://finance.yahoo.com/rss/headline?s={quote_plus(symbol)}",
                client.get_bytes,
            ),
            RssNewsSource(
                "GOOGLE_NEWS",
                lambda symbol: "https://news.google.com/rss/search?"
                f"q={quote_plus(canonical_news_query(symbol))}&hl=en-US&gl=US&ceid=US:en",
                client.get_bytes,
            ),
        ),
        retrieved_at=retrieved_at,
        scheduled_sources=(
            OfficialCalendarSource("FEDERAL_RESERVE", FED_URL, client.get_bytes, parse_fomc_calendar),
            OfficialCalendarSource("BLS", BLS_URL, client.get_bytes, parse_bls_ics),
            OfficialCalendarSource("FED_CHAIR_CALENDAR", fed_chair_calendar_url(retrieved_at.astimezone(ET).date()), client.get_bytes, parse_fed_chair_calendar),
        ),
    )


def _provider_health(config: OptionBotConfig) -> tuple[str, dict[str, int | str | bool]]:
    path = os.environ.get(
        "ROBINHOOD_RESEARCH_SNAPSHOT_PATH",
        "results/robinhood_option_research.json",
    )
    allowed, reason = validate_research_snapshot(
        path, now=datetime.now(ET), max_age_seconds=60
    )
    checks: dict[str, int | str | bool] = {
        "market_data_provider": config.market_data_provider,
        "research_snapshot": reason,
        "broker_execution_enabled": False,
        "live_trading_enabled": False,
    }
    return ("READY" if allowed else "UNAVAILABLE"), checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="option-bot")
    parser.add_argument("command", nargs="?", choices=COMMANDS, default="health")
    parser.add_argument("--force-expiry-holds", action="store_true", help="Explicitly override low-delta paper expiration holds when closing")
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
            research_path = os.environ.get(
                "ROBINHOOD_RESEARCH_SNAPSHOT_PATH",
                "results/robinhood_option_research.json",
            )
            rows = []
            for symbol in config.symbols:
                surface = load_robinhood_research_surface(
                    research_path, symbol, trade_date, datetime.now(ET)
                )
                rows.append({
                    "symbol": symbol,
                    "trade_date": trade_date,
                    "contract_count": len(surface.contracts),
                    "status": (
                        "AVAILABLE"
                        if surface.availability.value == "AVAILABLE"
                        else "DATA_UNAVAILABLE"
                    ),
                    "reason_codes": list(surface.reason_codes),
                    "source": "ROBINHOOD_MCP_RESEARCH",
                })
            report = {
                "module_id": "OPTION-001",
                "strategy_type": "0DTE_OPTIONS",
                "trade_date": trade_date,
                "paper_only": True,
                "order_submission_enabled": False,
                "symbols": rows,
            }
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
            now = datetime.now(ET)
            trade_date = args.trade_date or now.date().isoformat()
            report = daily_event_report(
                args.output_dir, trade_date, retrieved_at=now,
                collect=lambda: _event_report(config, now),
            )
            output = Path(args.output_dir) / "option_001_events.json"
            print(f"OPTION-001 event intelligence written for {len(config.symbols)} governed symbols: {output}")
            return 0
        except (ConfigError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(json.dumps({"status": "DATA_UNAVAILABLE", "paper_only": True, "detail": str(exc)}, sort_keys=True))
            return 2
    if command in {"manage-once", "close-all-paper"}:
        try:
            config = OptionBotConfig.load(os.environ, Path(args.config))
            as_of = datetime.now(ET)
            snapshot_path = os.environ.get("ROBINHOOD_RESEARCH_SNAPSHOT_PATH", "results/robinhood_option_research.json")
            result = LocalPaperSimulation(config).cycle((), snapshot_path, as_of,
                allow_entries=False, force_close=command == "close-all-paper",
                force_expiry_holds=args.force_expiry_holds)
            result["command"] = command
            # Shadow runs on the SAME management tick and on an isolated ledger.
            # Errors never alter OPTION-001's own risk/exit decisions.
            try:
                from option_bot.reversal_shadow_cycle import run_cycle
                run_cycle(config,Path(args.output_dir),as_of,
                          allow_entries=os.environ.get("SHADOW_EARLY_ENTRY_SCAN")=="1",
                          events=json.loads((Path(args.output_dir)/"option_001_scan_events.json").read_text())
                          if (Path(args.output_dir)/"option_001_scan_events.json").exists() else {})
            except (OSError,ValueError,TypeError,KeyError,ArithmeticError) as exc:
                print(json.dumps({"shadow_status":"DATA_UNAVAILABLE","shadow_reason":str(exc),
                     "paper_only":True,"broker_submissions":0}))
            refresh_paper_reports(Path(args.output_dir), result)
            if result["paper_execution_status"] == "DEGRADED":
                request_refresh(args.output_dir, command, "HELD_LEG_QUOTES_REQUIRED")
            else:
                complete_refresh(args.output_dir, result)
            print(json.dumps({"command": command, "open_count": len(result["open"]),
                "new_paper_events": result["new_events"], "status": result["paper_execution_status"],
                "paper_only": True, "broker_submissions": 0}, sort_keys=True))
            return 2 if result["paper_execution_status"] == "DEGRADED" else 0
        except (ConfigError, OSError, ValueError, KeyError, ArithmeticError) as exc:
            print(json.dumps({"status": "DATA_UNAVAILABLE", "paper_only": True, "detail": str(exc)}))
            return 2
    if command == "scan-once":
        try:
            config = OptionBotConfig.load(os.environ, Path(args.config))
            as_of = datetime.now(ET)
            trade_date = args.trade_date or as_of.date().isoformat()
            from option_bot.symbol_events import load_earnings_calendar
            earnings = load_earnings_calendar(Path(args.output_dir) / "option_001_earnings_calendar.json", trade_date)
            events = apply_scheduled_event_policy({**daily_event_report(args.output_dir, trade_date), "earnings_calendar": earnings, "scan_as_of_et": as_of.isoformat(), "event_risk_window": json.loads(Path(args.config).read_text()).get("event_risk_window", {"before_minutes": 30, "after_minutes": 30})})
            write_event_json(Path(args.output_dir) / "option_001_scan_events.json", {**events, "scan_as_of_et": as_of.isoformat()})
            model_path = Path("configs/evidence-model-v1.json")
            model = json.loads(model_path.read_text(encoding="utf-8"))
            research_path = os.environ.get("ROBINHOOD_RESEARCH_SNAPSHOT_PATH")
            if not research_path:
                raise ConfigError("ROBINHOOD_RESEARCH_SNAPSHOT_PATH is required")
            research_provider = lambda symbol, expiration, received_at: load_robinhood_research_surface(
                research_path, symbol, expiration, received_at
            )
            bars_provider = lambda symbol, received_at: load_robinhood_research_bars(
                research_path, symbol
            )
            forbidden_transport = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("Alpaca transport is disabled in Robinhood-only paper mode")
            )
            evaluations = evaluate_live_scan(
                symbols=tuple(s for s in ("SPX", "XSP") if s in config.symbols) + tuple(s for s in config.symbols if s not in {"SPX", "XSP"}), trade_date=trade_date, as_of=as_of,
                paper_transport=forbidden_transport, market_transport=forbidden_transport,
                event_report=events,
                evidence_engine=EvidenceEngine.from_file(model_path), max_loss=config.max_loss_per_trade,
                trade_threshold=int(model["trade_threshold"]), watch_threshold=int(model["watch_threshold"]),
                research_surface_provider=research_provider,
                research_bars_provider=bars_provider,
                max_loss_for_symbol=config.loss_limit_for,
                score_advisory=model.get("technical_score_policy") == "ADVISORY_DIRECTION_AND_RANKING",
                directional_credit_only=model.get("candidate_collection_policy") in {
                    "DIRECTION_FIRST_CREDIT_ONLY_V1",
                    "DIRECTION_FIRST_CREDIT_PLUS_CALL_DEBIT_V2",
                },
                call_debit_enabled=model.get("candidate_collection_policy") == "DIRECTION_FIRST_CREDIT_PLUS_CALL_DEBIT_V2",
                bollinger_condor=model.get("bollinger_condor_policy") == "BB20_5MIN_2SIGMA_PLUS_020_V1",
            )
            paper_result = LocalPaperSimulation(config).cycle(evaluations, research_path, as_of,
                allow_entries=trade_date == as_of.date().isoformat())
            paper_result["command"] = command
            # Evaluate early reversal with identical option-cycle timestamp,
            # event policy, quote metadata and completely separate paper book.
            try:
                from option_bot.reversal_shadow_cycle import run_cycle
                run_cycle(config,Path(args.output_dir),as_of,allow_entries=True,events=events)
            except (OSError,ValueError,TypeError,KeyError,ArithmeticError) as exc:
                print(json.dumps({"shadow_status":"DATA_UNAVAILABLE","shadow_reason":str(exc),
                      "paper_only":True,"broker_submissions":0}))
            bundle = build_scan_report(
                trade_date=trade_date, symbols=config.symbols, evaluations=evaluations,
                output_dir=Path(args.output_dir),
                order_submission_enabled=config.order_submission_enabled,
                paper_result=paper_result,
            )
            from option_bot.decision_log import record_scan
            record_scan(Path(args.output_dir), bundle, as_of,
                        json.loads(Path(args.config).read_text()), model)
            Path(args.output_dir, "option_001_summary.json").write_text(json.dumps(bundle.summary, indent=2))
            from option_bot.dashboard import DashboardRenderer
            Path(args.output_dir, "option_001_dashboard.html").write_text(DashboardRenderer().render(bundle))
            if paper_result["execution_rejections"] and any(
                "STALE" in rejection["reason"] or "UNAVAILABLE" in rejection["reason"]
                for rejection in paper_result["execution_rejections"]):
                request_refresh(args.output_dir, command, "FRESH_EXECUTABLE_LEG_QUOTES_REQUIRED")
            elif paper_result["paper_execution_status"] == "DEGRADED":
                request_refresh(args.output_dir, command, "HELD_LEG_QUOTES_REQUIRED")
            elif paper_result["snapshot_fresh"]:
                complete_refresh(args.output_dir, paper_result)
            print(
                f"OPTION-001 evaluated {len(evaluations)} governed symbols; "
                f"selected {bundle.summary['selected_count']} for local paper simulation; "
                f"broker submissions 0: {args.output_dir}/option_001_leaderboard.json"
            )
            return 2 if paper_result["paper_execution_status"] == "DEGRADED" else 0
        except (ConfigError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(json.dumps({"status": "DATA_UNAVAILABLE", "paper_only": True, "detail": str(exc)}, sort_keys=True))
            return 2
    print(f"{command}: requires configured paper-only runtime")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
