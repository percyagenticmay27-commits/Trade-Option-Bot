"""Conservative open-position lifecycle and exit precedence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from option_bot.domain import Position, PositionAction
from option_bot.payoff import PayoffProfile


ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class PositionSnapshot:
    option_data_fresh: bool
    current_debit: Decimal | None
    underlying_price: Decimal
    thesis_intact: bool
    invalidation_level: Decimal
    daily_stop_hit: bool


class PositionManager:
    def __init__(self, mandatory_exit: time = time(15, 30), profit_fraction: Decimal = Decimal("0.50"), max_loss_fraction: Decimal = Decimal("0.50")):
        self.mandatory_exit = mandatory_exit
        self.profit_fraction = profit_fraction
        self.max_loss_fraction = max_loss_fraction

    @staticmethod
    def _action(position: Position, action: str, reason: str, now: datetime) -> PositionAction:
        return PositionAction(position.position_id, action, reason, now)

    def evaluate(self, position: Position, snapshot: PositionSnapshot, now: datetime) -> PositionAction:
        if now.tzinfo is None:
            raise ValueError("position evaluation time must be timezone-aware")
        observed = now.astimezone(ET)
        candidate = position.candidate
        original_credit = candidate.net_credit.amount if candidate.net_credit else Decimal("0")

        if snapshot.daily_stop_hit:
            return self._action(position, "CLOSE", "DAILY_STOP", observed)
        if not snapshot.thesis_intact:
            return self._action(position, "CLOSE", "THESIS_INVALIDATED", observed)
        if snapshot.underlying_price <= snapshot.invalidation_level:
            return self._action(position, "CLOSE", "UNDERLYING_INVALIDATION", observed)
        if observed.time().replace(tzinfo=None) >= self.mandatory_exit:
            return self._action(position, "CLOSE", "MANDATORY_TIME_EXIT", observed)
        if not snapshot.option_data_fresh or snapshot.current_debit is None:
            return self._action(position, "DEGRADE", "OPTION_DATA_STALE", observed)
        if snapshot.current_debit <= original_credit * self.profit_fraction:
            return self._action(position, "CLOSE", "PROFIT_TARGET", observed)

        profile = PayoffProfile.evaluate(candidate.legs, original_credit, candidate.product.multiplier)
        current_loss = (snapshot.current_debit - original_credit) * candidate.product.multiplier
        if current_loss >= profile.maximum_loss.amount * self.max_loss_fraction:
            return self._action(position, "CLOSE", "HALF_MAX_LOSS", observed)
        return self._action(position, "HOLD", "THESIS_INTACT", observed)
