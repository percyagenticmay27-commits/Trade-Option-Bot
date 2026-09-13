"""Normalize Alpaca-shaped payloads without filling missing evidence."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from option_bot.domain import ExerciseStyle, ProductMetadata, SettlementType
from option_bot.providers.base import Availability, NormalizedOptionContract, OptionSurface


ET = ZoneInfo("America/New_York")
MAX_QUOTE_AGE_SECONDS = 60


def unavailable_surface(symbol: str, expiration: str, reason: str, **evidence: object) -> OptionSurface:
    return OptionSurface(symbol, expiration, (), "unknown", Availability.UNAVAILABLE, (reason,), {k: str(v) for k, v in evidence.items()})


def _decimal_string(value: Any, field: str) -> str:
    if value is None:
        raise ValueError(field)
    try:
        return str(Decimal(str(value)))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(field) from exc


def normalize_option_surface(
    symbol: str,
    expiration: str,
    payload: Mapping[str, Any],
    received_time: datetime,
) -> OptionSurface:
    if received_time.tzinfo is None:
        return unavailable_surface(symbol, expiration, "RECEIVED_TIME_NOT_AWARE")
    raw_contracts = payload.get("contracts") or payload.get("chain") or {}
    if not raw_contracts:
        return unavailable_surface(symbol, expiration, "EMPTY_OPTION_SURFACE")
    items = raw_contracts.values() if isinstance(raw_contracts, Mapping) else raw_contracts
    normalized: list[NormalizedOptionContract] = []
    failures: set[str] = set()
    for raw in items:
        try:
            quote = raw["latest_quote"]
            bid = Decimal(_decimal_string(quote.get("bid_price"), "bid"))
            ask = Decimal(_decimal_string(quote.get("ask_price"), "ask"))
            if ask < bid:
                failures.add("CROSSED_MARKET")
                continue
            source_time = datetime.fromisoformat(quote["timestamp"].replace("Z", "+00:00"))
            if source_time.tzinfo is None:
                failures.add("SOURCE_TIME_NOT_AWARE")
                continue
            source_et = source_time.astimezone(ET)
            received_et = received_time.astimezone(ET)
            age = (received_et - source_et).total_seconds()
            if age < -5 or age > MAX_QUOTE_AGE_SECONDS:
                failures.add("STALE_QUOTES")
                continue
            greeks = raw.get("greeks")
            if not greeks or raw.get("implied_volatility") is None:
                failures.add("MISSING_GREEKS")
                continue
            required_greeks = {key: _decimal_string(greeks.get(key), key) for key in ("delta", "gamma", "theta", "vega")}
            style = ExerciseStyle(str(raw.get("style", "american")).upper())
            product = ProductMetadata(
                symbol=symbol,
                multiplier=int(raw.get("size", 100)),
                exercise_style=style,
                settlement_type=SettlementType.PHYSICAL if style is ExerciseStyle.AMERICAN else SettlementType.CASH,
                last_trading_time="16:00",
            )
            normalized.append(NormalizedOptionContract(
                symbol=str(raw["symbol"]), bid=str(bid), ask=str(ask),
                bid_size=int(quote.get("bid_size", 0)), ask_size=int(quote.get("ask_size", 0)),
                delta=required_greeks["delta"], gamma=required_greeks["gamma"],
                theta=required_greeks["theta"], vega=required_greeks["vega"],
                iv=_decimal_string(raw.get("implied_volatility"), "iv"),
                volume=int(raw.get("volume") or 0), open_interest=int(raw.get("open_interest") or 0),
                source_time=source_et, received_time=received_et, product=product,
            ))
        except (KeyError, TypeError, ValueError):
            failures.add("MALFORMED_CONTRACT")
    if failures:
        return OptionSurface(symbol, expiration, tuple(normalized), str(payload.get("feed", "unknown")), Availability.UNAVAILABLE, tuple(sorted(failures)))
    if not normalized:
        return unavailable_surface(symbol, expiration, "EMPTY_OPTION_SURFACE")
    return OptionSurface(symbol, expiration, tuple(normalized), str(payload.get("feed", "unknown")), Availability.AVAILABLE)
