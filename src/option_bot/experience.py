"""Day-1 deterministic learner and shadow-only symbol experience ledger."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from option_bot.domain import Decision
from option_bot.evidence import EvidenceBundle


@dataclass(frozen=True)
class ExperienceProfile:
    symbol: str
    observations: int
    wins: int
    realized_pnl: Decimal

    @classmethod
    def empty(cls, symbol: str) -> "ExperienceProfile":
        return cls(symbol, 0, 0, Decimal("0"))


@dataclass(frozen=True)
class LearnerDecision:
    decision: Decision
    reason_codes: tuple[str, ...]
    evidence_score: int


@dataclass(frozen=True)
class OutcomeObservation:
    symbol: str
    won: bool
    realized_pnl: Decimal


@dataclass(frozen=True)
class ExperienceUpdate:
    profile: ExperienceProfile
    ranking_influence_enabled: bool = False


class ExperienceLearner:
    def __init__(self, trade_threshold: int, watch_threshold: int):
        self.trade_threshold = trade_threshold
        self.watch_threshold = watch_threshold

    def decide(self, evidence: EvidenceBundle, history: ExperienceProfile) -> LearnerDecision:
        del history  # Recorded for later shadow validation; prohibited from influencing Day-1 rank.
        if not evidence.available:
            return LearnerDecision(Decision.DATA_UNAVAILABLE, evidence.reason_codes or ("EVIDENCE_UNAVAILABLE",), 0)
        if evidence.direction_score >= self.trade_threshold:
            return LearnerDecision(Decision.TRADE, ("EVIDENCE_THRESHOLD_MET",), evidence.direction_score)
        if evidence.direction_score >= self.watch_threshold:
            return LearnerDecision(Decision.WATCH, ("EVIDENCE_INCOMPLETE",), evidence.direction_score)
        return LearnerDecision(Decision.NO_TRADE, ("EVIDENCE_THRESHOLD_NOT_MET",), evidence.direction_score)

    def observe(self, observation: OutcomeObservation, profile: ExperienceProfile) -> ExperienceUpdate:
        if observation.symbol != profile.symbol:
            raise ValueError("observation symbol must match experience profile")
        updated = ExperienceProfile(profile.symbol, profile.observations + 1, profile.wins + int(observation.won), profile.realized_pnl + observation.realized_pnl)
        return ExperienceUpdate(updated, False)
