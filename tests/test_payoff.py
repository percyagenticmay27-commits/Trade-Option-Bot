from decimal import Decimal

import pytest

from option_bot.domain import OptionLeg, OptionRight, TradeSide
from option_bot.payoff import PayoffProfile


EXPIRY = "2026-09-14"


def leg(symbol: str, right: OptionRight, side: TradeSide, strike: str, quantity: int = 1) -> OptionLeg:
    return OptionLeg(symbol, right, side, Decimal(strike), EXPIRY, quantity)


@pytest.mark.parametrize(
    ("legs", "credit", "max_profit", "max_loss", "breakevens"),
    [
        ((leg("P100S", OptionRight.PUT, TradeSide.SELL, "100"), leg("P99B", OptionRight.PUT, TradeSide.BUY, "99")), "0.30", "30.00", "70.00", (Decimal("99.70"),)),
        ((leg("C100S", OptionRight.CALL, TradeSide.SELL, "100"), leg("C101B", OptionRight.CALL, TradeSide.BUY, "101")), "0.25", "25.00", "75.00", (Decimal("100.25"),)),
        ((leg("P95B", OptionRight.PUT, TradeSide.BUY, "95"), leg("P96S", OptionRight.PUT, TradeSide.SELL, "96"), leg("C104S", OptionRight.CALL, TradeSide.SELL, "104"), leg("C105B", OptionRight.CALL, TradeSide.BUY, "105")), "0.40", "40.00", "60.00", (Decimal("95.60"), Decimal("104.40"))),
        ((leg("P94B", OptionRight.PUT, TradeSide.BUY, "94"), leg("P96S", OptionRight.PUT, TradeSide.SELL, "96"), leg("C104S", OptionRight.CALL, TradeSide.SELL, "104"), leg("C105B", OptionRight.CALL, TradeSide.BUY, "105")), "0.50", "50.00", "150.00", (Decimal("95.50"), Decimal("104.50"))),
        ((leg("P95B", OptionRight.PUT, TradeSide.BUY, "95"), leg("P100S", OptionRight.PUT, TradeSide.SELL, "100"), leg("C100S", OptionRight.CALL, TradeSide.SELL, "100"), leg("C105B", OptionRight.CALL, TradeSide.BUY, "105")), "1.50", "150.00", "350.00", (Decimal("98.50"), Decimal("101.50"))),
    ],
)
def test_exact_defined_risk_profiles(legs, credit, max_profit, max_loss, breakevens) -> None:
    profile = PayoffProfile.evaluate(legs, Decimal(credit), 100)
    assert profile.net_credit.amount == Decimal(credit) * 100
    assert profile.maximum_profit.amount == Decimal(max_profit)
    assert profile.maximum_loss.amount == Decimal(max_loss)
    assert profile.breakevens == breakevens


def test_arbitrary_four_leg_payoff_is_derived_from_actual_legs() -> None:
    legs = (
        leg("P90B", OptionRight.PUT, TradeSide.BUY, "90"),
        leg("P95S", OptionRight.PUT, TradeSide.SELL, "95"),
        leg("C100S", OptionRight.CALL, TradeSide.SELL, "100"),
        leg("C103B", OptionRight.CALL, TradeSide.BUY, "103"),
    )
    profile = PayoffProfile.evaluate(legs, Decimal("1.20"), 100)
    assert profile.pnl_at(Decimal("80")).amount == Decimal("-380.00")
    assert profile.pnl_at(Decimal("97")).amount == Decimal("120.00")
    assert profile.pnl_at(Decimal("110")).amount == Decimal("-180.00")


def test_rejects_undefined_risk_and_nonpositive_credit() -> None:
    naked_call = (leg("C100S", OptionRight.CALL, TradeSide.SELL, "100"),)
    with pytest.raises(ValueError, match="defined-risk"):
        PayoffProfile.evaluate(naked_call, Decimal("0.20"), 100)
    with pytest.raises(ValueError, match="credit"):
        PayoffProfile.evaluate((leg("P100S", OptionRight.PUT, TradeSide.SELL, "100"), leg("P99B", OptionRight.PUT, TradeSide.BUY, "99")), Decimal("0"), 100)
