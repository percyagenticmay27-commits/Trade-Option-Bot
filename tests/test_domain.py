from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from option_bot.domain import (
    EvidenceTimestamp,
    ExerciseStyle,
    Money,
    OptionLeg,
    OptionRight,
    Position,
    ProductMetadata,
    SettlementType,
    TradeCandidate,
    TradeSide,
)


def product() -> ProductMetadata:
    return ProductMetadata(
        symbol="AAPL",
        multiplier=100,
        exercise_style=ExerciseStyle.AMERICAN,
        settlement_type=SettlementType.PHYSICAL,
        last_trading_time="16:00",
    )


def legs() -> tuple[OptionLeg, ...]:
    expiry = "2026-09-14"
    return (
        OptionLeg("AAPL260914P00320000", OptionRight.PUT, TradeSide.SELL, Decimal("320"), expiry, 1),
        OptionLeg("AAPL260914P00319000", OptionRight.PUT, TradeSide.BUY, Decimal("319"), expiry, 1),
    )


def test_money_and_domain_objects_are_immutable() -> None:
    amount = Money(Decimal("10.00"), "USD")
    with pytest.raises(FrozenInstanceError):
        amount.amount = Decimal("12.00")  # type: ignore[misc]


def test_rejects_nonpositive_product_multiplier() -> None:
    with pytest.raises(ValueError, match="multiplier"):
        ProductMetadata("AAPL", 0, ExerciseStyle.AMERICAN, SettlementType.PHYSICAL, "16:00")


def test_rejects_mixed_expiration_candidate() -> None:
    mixed = list(legs())
    mixed[1] = OptionLeg(
        "AAPL260915P00319000", OptionRight.PUT, TradeSide.BUY,
        Decimal("319"), "2026-09-15", 1,
    )
    with pytest.raises(ValueError, match="same expiration"):
        TradeCandidate("candidate-1", "AAPL", tuple(mixed), product())


def test_requires_timezone_aware_evidence_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        EvidenceTimestamp(datetime(2026, 9, 14, 9, 45), datetime.now(timezone.utc))


def test_position_requires_complete_candidate() -> None:
    candidate = TradeCandidate("candidate-1", "AAPL", legs(), product())
    position = Position("position-1", candidate, datetime.now(timezone.utc))
    assert position.candidate.product.exercise_style is ExerciseStyle.AMERICAN
    assert position.candidate.product.settlement_type is SettlementType.PHYSICAL
