from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from option_bot.domain import Decision, StructureType
from option_bot.evidence import EvidenceBundle
from option_bot.live_scan import EvaluatedSetup, SetupEvaluator, build_scan_report
from option_bot.portfolio import SelectableCandidate
from option_bot.providers.base import Availability, EventGateEvidence, OptionSurface
from option_bot.indicators import IndicatorSnapshot


ET = ZoneInfo("America/New_York")


def test_scan_report_uses_evaluated_setups_instead_of_placeholder_rows(tmp_path: Path) -> None:
    """Catches scan wiring that discards evaluator output and emits blanket DATA_UNAVAILABLE."""
    candidate = SelectableCandidate(
        "AAPL", "AAPL-PUT_CREDIT_SPREAD-0.10", StructureType.PUT_CREDIT_SPREAD,
        Decimal("82"), Decimal("90"), "MEGA_CAP_TECH",
    )
    setup = EvaluatedSetup(
        symbol="AAPL", decision=Decision.TRADE, candidate=candidate,
        direction_score=82, range_score=0, premium_score=70,
        expected_value=Decimal("18.50"), reason_codes=(), evidence_id="scan:AAPL",
    )

    bundle = build_scan_report(
        trade_date="2026-09-15", symbols=("AAPL", "MSFT"),
        evaluations=(setup, EvaluatedSetup.unavailable("MSFT", ("STALE_QUOTES",))),
        output_dir=tmp_path, render=False,
    )

    assert bundle.leaderboard[0]["decision"] == "TRADE"
    assert bundle.leaderboard[0]["structure"] == "PUT_CREDIT_SPREAD"
    assert bundle.leaderboard[0]["expected_value"] == "18.50"
    assert bundle.leaderboard[1]["decision"] == "DATA_UNAVAILABLE"
    assert bundle.summary["selected_count"] == 1
    assert bundle.summary["health"] == "DEGRADED"


def test_scan_report_records_valid_no_trade_as_evaluated_not_pending(tmp_path: Path) -> None:
    """Catches valid rejected setups being mislabeled as missing provider data."""
    setup = EvaluatedSetup(
        symbol="AAPL", decision=Decision.NO_TRADE, candidate=None,
        direction_score=42, range_score=20, premium_score=70,
        expected_value=None, reason_codes=("SCORE_BELOW_THRESHOLD",), evidence_id="scan:AAPL",
    )
    bundle = build_scan_report(
        trade_date="2026-09-15", symbols=("AAPL",), evaluations=(setup,),
        output_dir=tmp_path, render=False,
    )
    assert bundle.leaderboard[0]["status"] == "EVALUATED"
    assert bundle.leaderboard[0]["decision"] == "NO_TRADE"
    assert bundle.summary["health"] == "HEALTHY"


def test_setup_evaluator_distinguishes_missing_evidence_from_rejected_structures() -> None:
    """Catches the composition layer mapping every non-trade outcome to DATA_UNAVAILABLE."""
    evidence = EvidenceBundle(True, 60, 0, 70, Decimal("1"), "v1", "hash", (), None, None)
    evaluator = SetupEvaluator(
        score=lambda *_: evidence,
        generate=lambda *_: (),
        trade_threshold=75,
        watch_threshold=55,
        max_loss=Decimal("100"),
    )
    indicators = IndicatorSnapshot(
        True, Decimal("200"), Decimal("199"), Decimal("200"), Decimal("199"),
        25, 40, 2, 1.2, Decimal("201"), Decimal("198"), Decimal("202"),
        Decimal("195"), 2, False,
    )
    events = EventGateEvidence("AAPL", Availability.AVAILABLE, False, ())

    result = evaluator.evaluate("AAPL", indicators, OptionSurface("AAPL", "2026-09-15", (), "indicative", Availability.AVAILABLE), events)

    assert result.decision is Decision.WATCH
    assert result.direction_score == 60
    assert "NO_VALID_STRUCTURE" in result.reason_codes


def test_scan_report_applies_two_entry_and_daily_defined_loss_limits(tmp_path: Path) -> None:
    """Catches qualified rows bypassing portfolio limits when reports mark selections."""
    setups = []
    for symbol, score in (("AAPL", "90"), ("TSLA", "85"), ("DJX", "80")):
        candidate = SelectableCandidate(symbol, f"{symbol}-candidate", StructureType.PUT_CREDIT_SPREAD, Decimal(score), Decimal("90"), symbol)
        setups.append(EvaluatedSetup(symbol, Decision.TRADE, candidate, 90, 0, 70, Decimal("10"), (), f"scan:{symbol}"))
    bundle = build_scan_report(trade_date="2026-09-15", symbols=("AAPL", "TSLA", "DJX"), evaluations=tuple(setups), output_dir=tmp_path, render=False)
    assert bundle.summary["selected_count"] == 2
    assert [row["symbol"] for row in bundle.positions["selected"]] == ["AAPL", "TSLA"]


def test_scan_report_ranks_evaluated_setups_by_score(tmp_path: Path) -> None:
    """Catches the leaderboard retaining config order instead of evidence rank."""
    low = EvaluatedSetup("AAPL", Decision.WATCH, None, 55, 0, 70, None, ("NO_VALID_STRUCTURE",), "a")
    high = EvaluatedSetup("MSFT", Decision.NO_TRADE, None, 70, 0, 70, None, ("NO_VALID_STRUCTURE",), "m")
    bundle = build_scan_report(trade_date="2026-09-15", symbols=("AAPL", "MSFT"), evaluations=(low, high), output_dir=tmp_path, render=False)
    assert [row["symbol"] for row in bundle.leaderboard] == ["MSFT", "AAPL"]
    assert [row["rank"] for row in bundle.leaderboard] == [1, 2]
