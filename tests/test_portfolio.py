from decimal import Decimal

from option_bot.domain import StructureType
from option_bot.portfolio import PortfolioSelector, SelectableCandidate


def item(symbol, structure, score, loss="80", sector="technology", justification=False):
    return SelectableCandidate(symbol, f"{symbol}-{structure.value}", structure, Decimal(score), Decimal(loss), sector, justification)


def test_selects_best_neutral_and_best_directional_up_to_two() -> None:
    ranked = (
        item("AAPL", StructureType.IRON_CONDOR, "9.0"),
        item("MSFT", StructureType.PUT_CREDIT_SPREAD, "8.5", sector="software"),
        item("TSLA", StructureType.PUT_CREDIT_SPREAD, "7.0", sector="consumer"),
    )
    result = PortfolioSelector().select(ranked, (), Decimal("0"), 0)
    assert [x.symbol for x in result.selected] == ["AAPL", "MSFT"]


def test_zero_one_and_daily_exhaustion() -> None:
    selector = PortfolioSelector()
    assert selector.select((), (), Decimal("0"), 0).selected == ()
    one = selector.select((item("AAPL", StructureType.IRON_CONDOR, "9"),), (), Decimal("0"), 0)
    assert len(one.selected) == 1
    exhausted = selector.select((item("AAPL", StructureType.IRON_CONDOR, "9"),), (), Decimal("200"), 2)
    assert exhausted.selected == () and "DAILY_LIMIT_EXHAUSTED" in exhausted.reason_codes


def test_correlated_semiconductor_exposure_is_rejected_without_justification() -> None:
    ranked = (
        item("NVDA", StructureType.PUT_CREDIT_SPREAD, "9", sector="semiconductors"),
        item("AVGO", StructureType.CALL_CREDIT_SPREAD, "8.9", sector="semiconductors"),
        item("AAPL", StructureType.CALL_CREDIT_SPREAD, "8", sector="technology"),
    )
    result = PortfolioSelector().select(ranked, (), Decimal("0"), 0)
    assert [x.symbol for x in result.selected] == ["NVDA", "AAPL"]
    assert result.rejected["AVGO"] == "CORRELATED_EXPOSURE"


def test_documented_correlation_justification_allows_pair() -> None:
    ranked = (
        item("NVDA", StructureType.PUT_CREDIT_SPREAD, "9", sector="semiconductors"),
        item("AVGO", StructureType.CALL_CREDIT_SPREAD, "8.9", sector="semiconductors", justification=True),
    )
    assert len(PortfolioSelector().select(ranked, (), Decimal("0"), 0).selected) == 2
