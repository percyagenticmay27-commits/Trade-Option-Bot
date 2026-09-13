import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from option_bot.providers.alpaca_market import AlpacaMarketDataClient
from option_bot.providers.base import Availability
from option_bot.providers.normalization import normalize_option_surface


FIXTURES = Path(__file__).parent / "fixtures" / "alpaca"
ET = ZoneInfo("America/New_York")
AS_OF = datetime(2026, 9, 14, 10, 0, 30, tzinfo=ET)


def payload(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_normalizes_active_chain_with_product_quotes_and_greeks() -> None:
    surface = normalize_option_surface("AAPL", "2026-09-14", payload("aapl_chain.json"), AS_OF)
    assert surface.availability is Availability.AVAILABLE
    quote = surface.contracts[0]
    assert quote.bid == "0.29" and quote.ask == "0.31"
    assert quote.delta == "-0.1023" and quote.gamma == "0.0292"
    assert quote.iv == "0.3514" and quote.volume == 87 and quote.open_interest == 321
    assert quote.product.multiplier == 100 and quote.source_time.tzinfo is not None
    assert surface.feed == "indicative"


@pytest.mark.parametrize(("name", "reason"), [("stale_chain.json", "STALE_QUOTES"), ("missing_greeks.json", "MISSING_GREEKS")])
def test_chain_fails_closed_for_stale_or_incomplete_data(name, reason) -> None:
    surface = normalize_option_surface("AAPL", "2026-09-14", payload(name), AS_OF)
    assert surface.availability is Availability.UNAVAILABLE
    assert reason in surface.reason_codes


def test_crossed_market_and_empty_index_coverage_are_unavailable() -> None:
    crossed = payload("aapl_chain.json")
    crossed["contracts"]["AAPL260914P00325000"]["latest_quote"].update(bid_price=0.35, ask_price=0.31)
    assert "CROSSED_MARKET" in normalize_option_surface("AAPL", "2026-09-14", crossed, AS_OF).reason_codes
    xsp = normalize_option_surface("XSP", "2026-09-14", payload("xsp_contracts.json"), AS_OF)
    assert xsp.reason_codes == ("EMPTY_OPTION_SURFACE",)


def test_market_client_retries_idempotent_reads_and_surfaces_rate_limit() -> None:
    calls = []
    def transport(method, path, params, body):
        calls.append(path)
        if len(calls) == 1:
            return 429, {"message": "rate limit"}
        return 200, payload("aapl_chain.json")
    client = AlpacaMarketDataClient(transport, max_read_attempts=2, sleeper=lambda _: None)
    surface = client.get_option_surface("AAPL", "2026-09-14", AS_OF)
    assert surface.availability is Availability.AVAILABLE and len(calls) == 2


def test_market_client_reports_timeout_and_empty_expiration() -> None:
    def timeout(*_):
        raise TimeoutError("network timeout")
    client = AlpacaMarketDataClient(timeout, max_read_attempts=1, sleeper=lambda _: None)
    assert client.get_option_surface("AAPL", "2026-09-14", AS_OF).reason_codes == ("PROVIDER_TIMEOUT",)
    assert client.get_option_surface("AAPL", "", AS_OF).reason_codes == ("EXPIRATION_REQUIRED",)
