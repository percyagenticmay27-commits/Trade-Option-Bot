from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from option_bot.config import PAPER_BASE_URL
from option_bot.domain import (
    ExerciseStyle, Money, OptionLeg, OptionRight, PaperMultiLegOrder, ProductMetadata,
    SettlementType, TradeCandidate, TradeSide,
)
from option_bot.providers.alpaca_paper import AlpacaPaperClient


ET = ZoneInfo("America/New_York")


def order() -> PaperMultiLegOrder:
    expiration = "2026-09-14"
    product = ProductMetadata("AAPL", 100, ExerciseStyle.AMERICAN, SettlementType.PHYSICAL, "16:00")
    legs = (
        OptionLeg("AAPL260914P00325000", OptionRight.PUT, TradeSide.SELL, Decimal("325"), expiration, 1),
        OptionLeg("AAPL260914P00324000", OptionRight.PUT, TradeSide.BUY, Decimal("324"), expiration, 1),
    )
    candidate = TradeCandidate("c-1", "AAPL", legs, product, Money(Decimal("0.30")))
    return PaperMultiLegOrder("local-1", candidate, Money(Decimal("0.30")), datetime(2026, 9, 14, 10, 0, tzinfo=ET))


def test_constructor_requires_exact_paper_endpoint() -> None:
    with pytest.raises(ValueError, match="paper endpoint"):
        AlpacaPaperClient("https://api.alpaca.markets", lambda *_: (200, {}))


def test_submit_uses_one_complete_multileg_order_and_never_retries() -> None:
    calls = []
    def transport(method, path, params, body):
        calls.append((method, path, body))
        return 201, {"id": "paper-123", "status": "accepted"}
    result = AlpacaPaperClient(PAPER_BASE_URL, transport).submit_multileg(order())
    assert result.status == "accepted" and len(calls) == 1
    assert calls[0][2]["order_class"] == "mleg" and len(calls[0][2]["legs"]) == 2


def test_timeout_is_unknown_and_not_retried() -> None:
    calls = []
    def timeout(*args):
        calls.append(args)
        raise TimeoutError
    result = AlpacaPaperClient(PAPER_BASE_URL, timeout).submit_multileg(order())
    assert result.status == "UNKNOWN" and len(calls) == 1


def test_cancel_is_idempotent_status_result() -> None:
    client = AlpacaPaperClient(PAPER_BASE_URL, lambda *_: (204, {}))
    assert client.cancel("paper-123").status == "CANCELED"
