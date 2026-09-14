"""Explicit paper-only operational command surface."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from option_bot.config import ConfigError, OptionBotConfig


COMMANDS = ("health", "scan-once", "manage-once", "close-all-paper", "render-reports")


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
            payload = {**config.safe_summary(), "database_writable": writable, "provider_status": "NOT_CHECKED"}
            print(json.dumps(payload, sort_keys=True))
            return 0 if writable else 2
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
