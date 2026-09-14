from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from option_bot.fills import FillModel, MultiLegQuote


ET = ZoneInfo("America/New_York")


def quote(at, natural, midpoint, complete=True):
    return MultiLegQuote(datetime(2026, 9, 14, *at, tzinfo=ET), Decimal(natural), Decimal(midpoint), complete)


def test_does_not_assume_midpoint_fill() -> None:
    decision = FillModel().evaluate(Decimal("0.30"), [quote((10, 0), "0.20", "0.35")])
    assert not decision.filled and decision.reason_code == "LIMIT_NOT_MARKETABLE"


def test_natural_fill_and_price_improvement_are_bounded_by_midpoint() -> None:
    decision = FillModel().evaluate(Decimal("0.30"), [quote((10, 0), "0.32", "0.36")])
    assert decision.filled
    assert Decimal("0.30") <= decision.fill_credit <= Decimal("0.36")


def test_incomplete_multileg_quote_rejected_and_unfilled_expires_at_1030() -> None:
    assert FillModel().evaluate(Decimal("0.30"), [quote((10, 0), "0.40", "0.45", False)]).reason_code == "INCOMPLETE_MULTI_LEG_QUOTE"
    expired = FillModel().evaluate(Decimal("0.30"), [quote((10, 31), "0.20", "0.35")])
    assert not expired.filled and expired.reason_code == "ENTRY_WINDOW_EXPIRED"
