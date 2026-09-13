import json
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from option_bot.evidence import EvidenceEngine
from option_bot.indicators import IndicatorEngine, load_bars_csv
from option_bot.providers.base import Availability, EventGateEvidence, OptionSurface


ROOT = Path(__file__).parents[1]
BARS = load_bars_csv(ROOT / "tests/fixtures/bars/aapl_intraday.csv")
MODEL = ROOT / "configs/evidence-model-v1.json"


def surface(available=True):
    return OptionSurface("AAPL", "2026-09-14", (), "indicative", Availability.AVAILABLE if available else Availability.UNAVAILABLE, () if available else ("MISSING_GREEKS",))


def test_scores_are_versioned_reproducible_and_probabilities_are_separate() -> None:
    snap = IndicatorEngine.compute(BARS, BARS, {"spy_above_vwap": True, "qqq_above_vwap": True, "sector_above_vwap": True, "previous_high": "99", "previous_low": "95", "average_volume": "1500"})
    events = EventGateEvidence("AAPL", Availability.AVAILABLE, False, ())
    first = EvidenceEngine.from_file(MODEL).score(snap, surface(), events)
    second = EvidenceEngine.from_file(MODEL).score(snap, surface(), events)
    assert first.direction_score == 100 and first.model_version == "evidence-model-v1"
    assert first.model_hash == second.model_hash
    assert first.canonical_json() == second.canonical_json()
    assert first.evidence_confidence == Decimal("1.00")
    assert first.implied_probability is None and first.calibrated_probability is None


def test_unavailable_inputs_block_scoring() -> None:
    snap = IndicatorEngine.compute(BARS, BARS, {"spy_above_vwap": True, "qqq_above_vwap": True, "sector_above_vwap": True, "previous_high": "99", "previous_low": "95", "average_volume": "1500"})
    events = EventGateEvidence("AAPL", Availability.AVAILABLE, False, ())
    result = EvidenceEngine.from_file(MODEL).score(snap, surface(False), events)
    assert not result.available and "OPTION_SURFACE_UNAVAILABLE" in result.reason_codes


def test_neutral_score_uses_adx_and_chop_not_direction_delta() -> None:
    snap = IndicatorEngine.compute(BARS, BARS, {"spy_above_vwap": True, "qqq_above_vwap": True, "sector_above_vwap": True, "previous_high": "99", "previous_low": "95", "average_volume": "1500"})
    neutral = replace(snap, adx14=15.0, chop14=60.0)
    result = EvidenceEngine.from_file(MODEL).score(neutral, surface(), EventGateEvidence("AAPL", Availability.AVAILABLE, False, ()))
    assert result.range_score == 100
