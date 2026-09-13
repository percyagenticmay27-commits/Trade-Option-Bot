"""Pure, deterministic intraday indicators used by the evidence engine."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


@dataclass(frozen=True)
class IndicatorSnapshot:
    available: bool
    price: Decimal
    vwap: Decimal
    ema9: Decimal
    ema20: Decimal
    adx14: float
    chop14: float
    atr14: float
    relative_volume: float
    opening_range_high: Decimal
    opening_range_low: Decimal
    previous_high: Decimal
    previous_low: Decimal
    market_alignment: int
    bullish_structure: bool
    reason_codes: tuple[str, ...] = ()


def load_bars_csv(path: Path) -> tuple[Bar, ...]:
    with path.open(newline="", encoding="utf-8") as handle:
        return tuple(Bar(
            datetime.fromisoformat(row["timestamp"]), Decimal(row["open"]), Decimal(row["high"]),
            Decimal(row["low"]), Decimal(row["close"]), int(row["volume"]),
        ) for row in csv.DictReader(handle))


def ema(values: Sequence[Decimal], period: int) -> tuple[Decimal, ...]:
    if not values or period <= 0:
        return ()
    alpha = Decimal(2) / Decimal(period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append((value * alpha) + (result[-1] * (Decimal(1) - alpha)))
    return tuple(result)


def session_vwap(bars: Sequence[Bar]) -> tuple[Decimal, ...]:
    result: list[Decimal] = []
    current_date = None
    cumulative_pv = Decimal(0)
    cumulative_volume = 0
    for bar in bars:
        if bar.timestamp.date() != current_date:
            current_date = bar.timestamp.date()
            cumulative_pv = Decimal(0)
            cumulative_volume = 0
        typical = (bar.high + bar.low + bar.close) / Decimal(3)
        cumulative_pv += typical * bar.volume
        cumulative_volume += bar.volume
        result.append(cumulative_pv / cumulative_volume)
    return tuple(result)


def _true_ranges(bars: Sequence[Bar]) -> list[float]:
    values = []
    for index, bar in enumerate(bars):
        if index == 0:
            values.append(float(bar.high - bar.low))
        else:
            previous = bars[index - 1].close
            values.append(float(max(bar.high - bar.low, abs(bar.high - previous), abs(bar.low - previous))))
    return values


def _wilder(values: Sequence[float], period: int) -> float:
    value = sum(values[:period]) / period
    for item in values[period:]:
        value = ((value * (period - 1)) + item) / period
    return value


def _adx(bars: Sequence[Bar], period: int) -> float:
    tr = _true_ranges(bars)
    plus_dm, minus_dm = [0.0], [0.0]
    for previous, current in zip(bars, bars[1:]):
        up = float(current.high - previous.high)
        down = float(previous.low - current.low)
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
    atr = _wilder(tr, period)
    plus = 100 * _wilder(plus_dm, period) / atr if atr else 0
    minus = 100 * _wilder(minus_dm, period) / atr if atr else 0
    return 100 * abs(plus - minus) / (plus + minus) if plus + minus else 0.0


class IndicatorEngine:
    @staticmethod
    def compute(bars_5m: Sequence[Bar], bars_15m: Sequence[Bar], market_context: Mapping[str, object]) -> IndicatorSnapshot:
        empty = Decimal(0)
        if len(bars_5m) < 20 or len(bars_15m) < 14:
            return IndicatorSnapshot(
                available=False, price=empty, vwap=empty, ema9=empty, ema20=empty,
                adx14=0, chop14=0, atr14=0, relative_volume=0,
                opening_range_high=empty, opening_range_low=empty,
                previous_high=empty, previous_low=empty, market_alignment=0,
                bullish_structure=False, reason_codes=("INSUFFICIENT_BARS",),
            )
        closes = [bar.close for bar in bars_5m]
        tr = _true_ranges(bars_5m)
        atr = _wilder(tr, 14)
        recent = bars_5m[-14:]
        high = max(float(bar.high) for bar in recent)
        low = min(float(bar.low) for bar in recent)
        tr_sum = sum(tr[-14:])
        chop = 100 * math.log10(tr_sum / (high - low)) / math.log10(14) if high > low else 100.0
        opening = [bar for bar in bars_5m if time(9, 30) <= bar.timestamp.timetz().replace(tzinfo=None) < time(9, 45)]
        average_volume = float(market_context.get("average_volume", 0) or 0)
        price = closes[-1]
        previous_high = Decimal(str(market_context.get("previous_high", price)))
        previous_low = Decimal(str(market_context.get("previous_low", price)))
        alignment = sum(bool(market_context.get(key, False)) for key in ("spy_above_vwap", "qqq_above_vwap", "sector_above_vwap"))
        return IndicatorSnapshot(
            True, price, session_vwap(bars_5m)[-1], ema(closes, 9)[-1], ema(closes, 20)[-1],
            _adx(bars_5m, 14), chop, atr,
            float(bars_5m[-1].volume) / average_volume if average_volume else 0.0,
            max(bar.high for bar in opening), min(bar.low for bar in opening), previous_high, previous_low,
            alignment, price > previous_high,
        )
