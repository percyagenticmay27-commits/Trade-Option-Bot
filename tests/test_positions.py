from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from option_bot.domain import ExerciseStyle, Money, OptionLeg, OptionRight, Position, ProductMetadata, SettlementType, TradeCandidate, TradeSide
from option_bot.positions import PositionManager, PositionSnapshot


ET = ZoneInfo("America/New_York")


def position() -> Position:
    expiry = "2026-09-14"
    product = ProductMetadata("AAPL", 100, ExerciseStyle.AMERICAN, SettlementType.PHYSICAL, "16:00")
    legs = (
        OptionLeg("P100S", OptionRight.PUT, TradeSide.SELL, Decimal("100"), expiry, 1),
        OptionLeg("P99B", OptionRight.PUT, TradeSide.BUY, Decimal("99"), expiry, 1),
    )
    candidate = TradeCandidate("c-1", "AAPL", legs, product, Money(Decimal("0.30")))
    return Position("p-1", candidate, datetime(2026, 9, 14, 10, 0, tzinfo=ET))


def snap(debit="0.30", price="101", **kwargs):
    values = dict(option_data_fresh=True, current_debit=Decimal(debit), underlying_price=Decimal(price), thesis_intact=True, invalidation_level=Decimal("99.50"), daily_stop_hit=False)
    values.update(kwargs)
    return PositionSnapshot(**values)


def evaluate(snapshot, hour=11, minute=0):
    return PositionManager().evaluate(position(), snapshot, datetime(2026, 9, 14, hour, minute, tzinfo=ET))


def test_profit_target_exit() -> None:
    assert evaluate(snap("0.15")).reason_code == "PROFIT_TARGET"


@pytest.mark.parametrize(("snapshot", "reason"), [
    (snap(thesis_intact=False), "THESIS_INVALIDATED"),
    (snap(price="99.40"), "UNDERLYING_INVALIDATION"),
    (snap("0.65"), "HALF_MAX_LOSS"),
    (snap(daily_stop_hit=True), "DAILY_STOP"),
])
def test_active_risk_exits(snapshot, reason) -> None:
    assert evaluate(snapshot).reason_code == reason


def test_stale_option_data_creates_degraded_state_but_underlying_guard_remains() -> None:
    degraded = evaluate(snap(option_data_fresh=False, current_debit=None))
    assert degraded.action == "DEGRADE" and degraded.reason_code == "OPTION_DATA_STALE"
    breached = evaluate(snap(option_data_fresh=False, current_debit=None, price="99.40"))
    assert breached.action == "CLOSE" and breached.reason_code == "UNDERLYING_INVALIDATION"


def test_mandatory_exit_at_1530() -> None:
    assert evaluate(snap(), 15, 30).reason_code == "MANDATORY_TIME_EXIT"
