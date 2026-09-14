"""Explicit paper-only operational command surface."""

from __future__ import annotations

import argparse


COMMANDS = ("health", "scan-once", "manage-once", "close-all-paper", "render-reports")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="option-bot")
    parser.add_argument("command", nargs="?", choices=COMMANDS, default="health")
    return parser


def main(argv: list[str] | None = None) -> int:
    command = build_parser().parse_args(argv).command
    if command == "health":
        print("OPTION-001 paper-only health: configuration required")
        return 0
    print(f"{command}: requires configured paper-only runtime")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
