"""Fail-closed configuration for OPTION-001."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import time
from decimal import Decimal
from pathlib import Path
from typing import Mapping

from .domain import OperatingMode, StrategyType


PAPER_BASE_URL = "https://paper-api.alpaca.markets"
REQUIRED_SYMBOLS = (
    "NVDA", "GOOGL", "AAPL", "MSFT", "AMZN", "META", "AVGO", "TSLA",
    "XSP", "MRUT", "MBTX", "DJX",
)


class ConfigError(ValueError):
    """Raised when paper-only safety cannot be proven."""


def _parse_time(value: str, field: str) -> time:
    try:
        hour, minute = value.split(":", maxsplit=1)
        return time(hour=int(hour), minute=int(minute))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ConfigError(f"{field} must be HH:MM") from exc


@dataclass(frozen=True)
class OptionBotConfig:
    module_id: str
    strategy_type: StrategyType
    enabled_strategy_types: tuple[StrategyType, ...]
    symbols: tuple[str, ...]
    operating_mode: OperatingMode
    paper_only: bool
    alpaca_key_id: str
    alpaca_secret_key: str
    alpaca_base_url: str
    timezone: str
    database_path: Path
    max_loss_per_trade: Decimal
    max_daily_defined_loss: Decimal
    max_daily_entries: int
    entry_start: time
    entry_end: time
    mandatory_exit: time

    @classmethod
    def load(cls, environment: Mapping[str, str], config_path: Path) -> "OptionBotConfig":
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"unable to read configuration: {config_path}") from exc

        for name in ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY"):
            if not environment.get(name):
                raise ConfigError(f"{name} is required")

        base_url = environment.get("APCA_API_BASE_URL", "")
        if base_url != PAPER_BASE_URL:
            raise ConfigError(f"Alpaca paper endpoint must be exactly {PAPER_BASE_URL}")

        timezone_name = environment.get("OPTION_BOT_TIMEZONE", "")
        if timezone_name != "America/New_York":
            raise ConfigError("OPTION_BOT_TIMEZONE must be America/New_York")

        symbols = tuple(raw.get("symbols", ()))
        if symbols != REQUIRED_SYMBOLS:
            raise ConfigError("symbol universe must match the governed OPTION-001 ordering")

        strategy_type = StrategyType(raw.get("strategy_type"))
        enabled = tuple(StrategyType(item) for item in raw.get("enabled_strategy_types", ()))
        if strategy_type is not StrategyType.ODTE_OPTIONS or enabled != (StrategyType.ODTE_OPTIONS,):
            raise ConfigError("only 0DTE_OPTIONS may be enabled in Version 1")

        max_trade = Decimal(str(raw.get("max_loss_per_trade")))
        max_daily = Decimal(str(raw.get("max_daily_defined_loss")))
        max_entries = int(raw.get("max_daily_entries"))
        if max_trade != Decimal("100.00") or max_daily != Decimal("200.00") or max_entries != 2:
            raise ConfigError("OPTION-001 risk limits must be $100/$200/two entries")

        entry_start = _parse_time(raw.get("entry_start"), "entry_start")
        entry_end = _parse_time(raw.get("entry_end"), "entry_end")
        mandatory_exit = _parse_time(raw.get("mandatory_exit"), "mandatory_exit")
        if not (entry_start == time(9, 45) and entry_end == time(10, 30) and mandatory_exit == time(15, 30)):
            raise ConfigError("OPTION-001 schedule must be 09:45/10:30/15:30 ET")

        if raw.get("module_id") != "OPTION-001":
            raise ConfigError("module_id must be OPTION-001")

        return cls(
            module_id="OPTION-001",
            strategy_type=strategy_type,
            enabled_strategy_types=enabled,
            symbols=symbols,
            operating_mode=OperatingMode.PAPER,
            paper_only=True,
            alpaca_key_id=environment["APCA_API_KEY_ID"],
            alpaca_secret_key=environment["APCA_API_SECRET_KEY"],
            alpaca_base_url=base_url,
            timezone=timezone_name,
            database_path=Path(environment.get("OPTION_BOT_DB_PATH", "results/option_bot.sqlite3")),
            max_loss_per_trade=max_trade,
            max_daily_defined_loss=max_daily,
            max_daily_entries=max_entries,
            entry_start=entry_start,
            entry_end=entry_end,
            mandatory_exit=mandatory_exit,
        )

    def safe_summary(self) -> dict[str, object]:
        return {
            "module_id": self.module_id,
            "strategy_type": self.strategy_type.value,
            "paper_only": self.paper_only,
            "alpaca_base_url": self.alpaca_base_url,
            "timezone": self.timezone,
            "symbol_count": len(self.symbols),
        }
