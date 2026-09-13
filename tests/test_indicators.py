from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from option_bot.indicators import Bar, IndicatorEngine, ema, load_bars_csv, session_vwap


FIXTURE = Path(__file__).parent / "fixtures" / "bars" / "aapl_intraday.csv"


def test_session_vwap_resets_between_dates() -> None:
    bars = load_bars_csv(FIXTURE)
    next_day = Bar(datetime.fromisoformat("2026-09-15T09:30:00-04:00"), Decimal("200"), Decimal("201"), Decimal("199"), Decimal("200"), 10)
    values = session_vwap((*bars, next_day))
    assert values[-1] == Decimal("200")


def test_exact_ema_seed_and_progression() -> None:
    assert ema([Decimal("1"), Decimal("2"), Decimal("3")], 2) == (Decimal("1"), Decimal("1.666666666666666666666666666"), Decimal("2.555555555555555555555555555"))


def test_indicator_snapshot_contains_required_directional_evidence() -> None:
    bars = load_bars_csv(FIXTURE)
    snap = IndicatorEngine.compute(bars, bars, {"spy_above_vwap": True, "qqq_above_vwap": True, "sector_above_vwap": True, "previous_high": "99", "previous_low": "95", "average_volume": "1500"})
    assert snap.price > snap.vwap
    assert snap.ema9 > snap.ema20
    assert snap.adx14 == pytest.approx(100.0)
    assert snap.atr14 == pytest.approx(2.0)
    assert snap.opening_range_high == Decimal("103") and snap.opening_range_low == Decimal("99")
    assert snap.previous_high == Decimal("99") and snap.relative_volume > 1
    assert snap.market_alignment == 3


def test_insufficient_bars_propagates_unavailable() -> None:
    snap = IndicatorEngine.compute(load_bars_csv(FIXTURE)[:10], [], {})
    assert not snap.available and "INSUFFICIENT_BARS" in snap.reason_codes
