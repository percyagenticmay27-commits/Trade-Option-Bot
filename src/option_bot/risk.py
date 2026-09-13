"""Non-bypassable paper-trading risk admission rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from option_bot.domain import GateDecision, OperatingMode, PortfolioRiskState, TradeCandidate
from option_bot.payoff import PayoffProfile


ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class RiskGovernor:
    per_trade_limit: Decimal = Decimal("100.00")
    daily_limit: Decimal = Decimal("200.00")
    daily_entry_limit: int = 2
    entry_start: time = time(9, 45)
    entry_end: time = time(10, 30)
    mandatory_exit: time = time(15, 30)

    @staticmethod
    def _reject(code: str, **evidence: object) -> GateDecision:
        return GateDecision(False, (code,), {key: str(value) for key, value in evidence.items()})

    def validate_candidate(
        self,
        candidate: TradeCandidate,
        portfolio: PortfolioRiskState,
        now: datetime,
    ) -> GateDecision:
        if now.tzinfo is None:
            return self._reject("TIMEZONE_REQUIRED")
        observed = now.astimezone(ET)
        if candidate.operating_mode is not OperatingMode.PAPER:
            return self._reject("PAPER_MODE_REQUIRED", operating_mode=candidate.operating_mode)
        if candidate.net_credit is None:
            return self._reject("MISSING_NET_CREDIT")
        if portfolio.trade_date != observed.date().isoformat():
            return self._reject("TRADE_DATE_MISMATCH", portfolio_date=portfolio.trade_date, observed_date=observed.date())
        expiry = candidate.legs[0].expiration
        if expiry != observed.date().isoformat():
            return self._reject("SAME_DAY_EXPIRATION_REQUIRED", expiration=expiry, observed_date=observed.date())
        if portfolio.entry_count >= self.daily_entry_limit:
            return self._reject("DAILY_ENTRY_LIMIT", entry_count=portfolio.entry_count)
        if observed.time().replace(tzinfo=None) < self.entry_start:
            return self._reject("BEFORE_ENTRY_WINDOW", observed_time=observed.strftime("%H:%M:%S"))
        if observed.time().replace(tzinfo=None) > self.entry_end:
            return self._reject("AFTER_ENTRY_WINDOW", observed_time=observed.strftime("%H:%M:%S"))

        try:
            profile = PayoffProfile.evaluate(
                candidate.legs,
                candidate.net_credit.amount,
                candidate.product.multiplier,
            )
        except ValueError as exc:
            return self._reject("INVALID_DEFINED_RISK_STRUCTURE", detail=exc)

        maximum_loss = profile.maximum_loss.amount
        if maximum_loss > self.per_trade_limit:
            return self._reject(
                "PER_TRADE_LOSS_LIMIT",
                maximum_loss=maximum_loss.quantize(Decimal("0.01")),
                limit=self.per_trade_limit,
                minimum_contracts=1,
            )
        aggregate = portfolio.defined_loss.amount + maximum_loss
        if aggregate > self.daily_limit:
            return self._reject(
                "DAILY_LOSS_LIMIT",
                aggregate_loss=aggregate.quantize(Decimal("0.01")),
                limit=self.daily_limit,
            )
        return GateDecision(
            True,
            (),
            {
                "maximum_loss": str(maximum_loss.quantize(Decimal("0.01"))),
                "aggregate_loss": str(aggregate.quantize(Decimal("0.01"))),
                "entry_count_after": str(portfolio.entry_count + 1),
                "mandatory_exit_et": self.mandatory_exit.strftime("%H:%M"),
            },
        )
