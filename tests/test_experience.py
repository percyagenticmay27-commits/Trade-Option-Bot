from decimal import Decimal

from option_bot.domain import Decision
from option_bot.evidence import EvidenceBundle
from option_bot.experience import ExperienceLearner, ExperienceProfile, OutcomeObservation


def evidence(score=80, available=True):
    return EvidenceBundle(available, score, 30, 70, Decimal("1.00"), "v1", "abc", (), None, None)


def test_day_one_learner_is_deterministic_and_uses_numeric_evidence() -> None:
    learner = ExperienceLearner(trade_threshold=75, watch_threshold=55)
    a = learner.decide(evidence(), ExperienceProfile.empty("AAPL"))
    b = learner.decide(evidence(), ExperienceProfile.empty("AAPL"))
    assert a == b and a.decision is Decision.TRADE


def test_watch_no_trade_and_unavailable_are_distinct() -> None:
    learner = ExperienceLearner(75, 55)
    profile = ExperienceProfile.empty("AAPL")
    assert learner.decide(evidence(60), profile).decision is Decision.WATCH
    assert learner.decide(evidence(40), profile).decision is Decision.NO_TRADE
    assert learner.decide(evidence(0, False), profile).decision is Decision.DATA_UNAVAILABLE


def test_observation_updates_symbol_specific_counts_without_influencing_rank() -> None:
    update = ExperienceLearner(75, 55).observe(OutcomeObservation("AAPL", True, Decimal("25.00")), ExperienceProfile.empty("AAPL"))
    assert update.profile.observations == 1 and update.profile.wins == 1
    assert update.profile.realized_pnl == Decimal("25.00")
    assert not update.ranking_influence_enabled
