from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from option_bot.domain import (
    ExerciseStyle, Money, OperatingMode, OptionLeg, OptionRight, PortfolioRiskState,
    ProductMetadata, SettlementType, TradeCandidate, TradeSide,
)
from option_bot.risk import RiskGovernor


ET = ZoneInfo("America/New_York")
EXPIRY = "2026-09-14"


def candidate(width: str = "1", credit: str = "0.50", mode: OperatingMode = OperatingMode.PAPER) -> TradeCandidate:
    short = Decimal("100")
    long = short - Decimal(width)
    product = ProductMetadata("AAPL", 100, ExerciseStyle.AMERICAN, SettlementType.PHYSICAL, "16:00")
    legs = (
        OptionLeg("P100S", OptionRight.PUT, TradeSide.SELL, short, EXPIRY, 1),
        OptionLeg("PLO", OptionRight.PUT, TradeSide.BUY, long, EXPIRY, 1),
    )
    return TradeCandidate("candidate-1", "AAPL", legs, product, Money(Decimal(credit)), mode)


def state(entries: int = 0, loss: str = "0") -> PortfolioRiskState:
    return PortfolioRiskState(EXPIRY, entries, Money(Decimal(loss)))


def now(hour: int = 10, minute: int = 0) -> datetime:
    return datetime(2026, 9, 14, hour, minute, tzinfo=ET)


def test_accepts_exactly_100_dollars_maximum_loss() -> None:
    decision = RiskGovernor().validate_candidate(candidate("1.50", "0.50"), state(), now())
    assert decision.allowed
    assert decision.evidence["maximum_loss"] == "100.00"


def test_rejects_100_01_and_unresizable_one_contract() -> None:
    decision = RiskGovernor().validate_candidate(candidate("1.5001", "0.50"), state(), now())
    assert not decision.allowed
    assert "PER_TRADE_LOSS_LIMIT" in decision.reason_codes
    assert decision.evidence["minimum_contracts"] == "1"


def test_rejects_daily_aggregate_above_200() -> None:
    decision = RiskGovernor().validate_candidate(candidate("1", "0.50"), state(loss="151"), now())
    assert decision.reason_codes == ("DAILY_LOSS_LIMIT",)


def test_rejects_third_entry() -> None:
    decision = RiskGovernor().validate_candidate(candidate(), state(entries=2), now())
    assert decision.reason_codes == ("DAILY_ENTRY_LIMIT",)


@pytest.mark.parametrize(("at", "reason"), [(now(9, 44), "BEFORE_ENTRY_WINDOW"), (now(10, 31), "AFTER_ENTRY_WINDOW")])
def test_entry_window_is_enforced(at, reason) -> None:
    assert RiskGovernor().validate_candidate(candidate(), state(), at).reason_codes == (reason,)


def test_rejects_any_nonpaper_mode() -> None:
    # The enum itself intentionally has no LIVE member; malformed external data is still rejected.
    item = candidate()
    object.__setattr__(item, "operating_mode", "LIVE")
    assert RiskGovernor().validate_candidate(item, state(), now()).reason_codes == ("PAPER_MODE_REQUIRED",)


def test_rejects_missing_credit_and_wrong_trade_date() -> None:
    item = candidate()
    object.__setattr__(item, "net_credit", None)
    assert RiskGovernor().validate_candidate(item, state(), now()).reason_codes == ("MISSING_NET_CREDIT",)
    assert RiskGovernor().validate_candidate(candidate(), PortfolioRiskState("2026-09-13", 0, Money(Decimal("0"))), now()).reason_codes == ("TRADE_DATE_MISMATCH",)
