"""Rank governed delta candidates by net expected value and execution quality."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from option_bot.probability import OutcomeDistribution, expected_net_value


@dataclass(frozen=True)
class OptimizationCandidate:
    candidate_id: str
    credit: Decimal
    maximum_loss: Decimal
    short_delta: Decimal
    boundary_clearance: Decimal
    gamma: Decimal
    distribution: OutcomeDistribution
    liquidity_score: Decimal = Decimal("1")
    experience_adjustment: Decimal = Decimal("0")


@dataclass(frozen=True)
class RankedCandidate:
    candidate: OptimizationCandidate
    expected_value: Decimal
    efficiency: Decimal
    experience_contribution: Decimal
    rank_score: Decimal


class DeltaOptimizer:
    @staticmethod
    def rank(candidates: Sequence[OptimizationCandidate], slippage: Decimal, fees: Decimal, experience_validated: bool = False) -> tuple[RankedCandidate, ...]:
        ranked = []
        for candidate in candidates:
            ev = expected_net_value(candidate.distribution.outcomes, slippage, fees)
            efficiency = candidate.credit / candidate.maximum_loss if candidate.maximum_loss else Decimal("0")
            experience = candidate.experience_adjustment if experience_validated else Decimal("0")
            quality = candidate.boundary_clearance + candidate.liquidity_score - candidate.gamma - candidate.distribution.stop_probability
            ranked.append(RankedCandidate(candidate, ev, efficiency, experience, ev + efficiency + quality + experience))
        return tuple(sorted(ranked, key=lambda item: (item.rank_score, item.expected_value), reverse=True))
