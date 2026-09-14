from decimal import Decimal

import pytest

from option_bot.probability import Outcome, OutcomeDistribution, ProbabilityContext, ProbabilityModel, expected_net_value


def test_outcome_probabilities_are_mutually_exclusive_and_sum_to_one() -> None:
    result = ProbabilityModel().estimate(ProbabilityContext("probability-v1", Decimal("0.68"), Decimal("0.22"), Decimal("0.14"), Decimal("0.11")))
    assert sum(item.probability for item in result.outcomes) == Decimal("1.0000")
    assert result.finish_probability == Decimal("0.68")
    assert result.touch_probability == Decimal("0.22")
    assert result.stop_probability == Decimal("0.14")
    assert result.target_probability == Decimal("0.11")
    assert result.range_probability is not None and result.time_exit_probability is not None


def test_expected_net_value_uses_all_outcomes_slippage_and_fees() -> None:
    outcomes = (Outcome("target", Decimal("0.60"), Decimal("30")), Outcome("stop", Decimal("0.40"), Decimal("-50")))
    assert expected_net_value(outcomes, Decimal("1.25"), Decimal("0.65")) == Decimal("-3.90")


def test_rejects_unversioned_assumptions_and_bad_probability_total() -> None:
    with pytest.raises(ValueError, match="version"):
        ProbabilityModel().estimate(ProbabilityContext("", Decimal("0.5"), Decimal("0.4"), Decimal("0.2"), Decimal("0.2")))
    with pytest.raises(ValueError, match="sum"):
        OutcomeDistribution((Outcome("a", Decimal("0.7"), Decimal("1")), Outcome("b", Decimal("0.4"), Decimal("-1"))), Decimal(".5"), Decimal(".5"), Decimal(".5"), Decimal(".5"), Decimal(".5"), Decimal(".5"), "v1")


def test_touch_probability_is_independent_input_not_doubled_delta() -> None:
    result = ProbabilityModel().estimate(ProbabilityContext("v1", Decimal("0.80"), Decimal("0.27"), Decimal("0.10"), Decimal("0.20")))
    assert result.touch_probability == Decimal("0.27")
    assert result.touch_probability != Decimal("0.40")
