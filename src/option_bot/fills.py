"""Conservative paper fill model that never assumes midpoint execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from typing import Sequence
from zoneinfo import ZoneInfo


ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class MultiLegQuote:
    timestamp: datetime
    natural_credit: Decimal
    midpoint_credit: Decimal
    complete: bool


@dataclass(frozen=True)
class FillDecision:
    filled: bool
    fill_credit: Decimal | None
    reason_code: str
    observed_at: datetime | None


class FillModel:
    def __init__(self, entry_deadline: time = time(10, 30)):
        self.entry_deadline = entry_deadline

    def evaluate(self, limit_credit: Decimal, quote_sequence: Sequence[MultiLegQuote]) -> FillDecision:
        if limit_credit <= 0:
            return FillDecision(False, None, "INVALID_LIMIT", None)
        for quote in quote_sequence:
            if quote.timestamp.tzinfo is None:
                return FillDecision(False, None, "QUOTE_TIME_NOT_AWARE", quote.timestamp)
            observed = quote.timestamp.astimezone(ET)
            if observed.time().replace(tzinfo=None) > self.entry_deadline:
                return FillDecision(False, None, "ENTRY_WINDOW_EXPIRED", observed)
            if not quote.complete:
                return FillDecision(False, None, "INCOMPLETE_MULTI_LEG_QUOTE", observed)
            if quote.natural_credit >= limit_credit:
                fill = min(quote.natural_credit, quote.midpoint_credit)
                fill = max(fill, limit_credit)
                return FillDecision(True, fill, "NATURAL_LIMIT_FILLED", observed)
        observed = quote_sequence[-1].timestamp if quote_sequence else None
        return FillDecision(False, None, "LIMIT_NOT_MARKETABLE", observed)
