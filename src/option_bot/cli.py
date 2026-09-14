"""Explicit paper-only operational command surface."""

from __future__ import annotations

import argparse
from pathlib import Path


COMMANDS = ("health", "scan-once", "manage-once", "close-all-paper", "render-reports")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="option-bot")
    parser.add_argument("command", nargs="?", choices=COMMANDS, default="health")
    parser.add_argument("--fixture-date")
    parser.add_argument("--output-dir", default="results")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command
    if command == "health":
        print("OPTION-001 paper-only health: configuration required")
        return 0
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
