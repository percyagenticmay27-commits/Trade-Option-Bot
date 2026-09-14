from decimal import Decimal

from option_bot.delta_optimizer import DeltaOptimizer, OptimizationCandidate
from option_bot.probability import Outcome, OutcomeDistribution


def distribution(win, loss, stop):
    return OutcomeDistribution((Outcome("win", Decimal("0.7"), Decimal(win)), Outcome("loss", Decimal("0.3"), Decimal(loss))), Decimal(".7"), Decimal(".25"), Decimal(stop), Decimal(".5"), Decimal(".4"), Decimal(".1"), "v1")


def test_ranks_expected_value_before_raw_premium() -> None:
    high_premium_bad_ev = OptimizationCandidate("high", Decimal("60"), Decimal("100"), Decimal("0.20"), Decimal("0.8"), Decimal("0.04"), distribution("30", "-90", ".3"))
    lower_premium_good_ev = OptimizationCandidate("best", Decimal("40"), Decimal("80"), Decimal("0.15"), Decimal("0.9"), Decimal("0.02"), distribution("40", "-20", ".1"))
    ranked = DeltaOptimizer.rank((high_premium_bad_ev, lower_premium_good_ev), Decimal("1"), Decimal("0.50"))
    assert ranked[0].candidate.candidate_id == "best"
    assert ranked[0].expected_value == Decimal("20.50")


def test_experience_adjustment_is_ignored_until_shadow_validation() -> None:
    item = OptimizationCandidate("one", Decimal("40"), Decimal("80"), Decimal("0.15"), Decimal("0.9"), Decimal("0.02"), distribution("40", "-20", ".1"), experience_adjustment=Decimal("999"))
    ranked = DeltaOptimizer.rank((item,), Decimal("0"), Decimal("0"), experience_validated=False)
    assert ranked[0].experience_contribution == Decimal("0")
