"""Versioned probability contracts and exact expected-value arithmetic."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence


@dataclass(frozen=True)
class Outcome:
    name: str
    probability: Decimal
    net_pnl: Decimal

    def __post_init__(self) -> None:
        if not Decimal("0") <= self.probability <= Decimal("1"):
            raise ValueError("outcome probability must be between zero and one")


@dataclass(frozen=True)
class OutcomeDistribution:
    outcomes: tuple[Outcome, ...]
    finish_probability: Decimal
    touch_probability: Decimal
    stop_probability: Decimal
    target_probability: Decimal
    range_probability: Decimal
    time_exit_probability: Decimal
    model_version: str

    def __post_init__(self) -> None:
        if not self.model_version:
            raise ValueError("probability model version is required")
        if abs(sum((item.probability for item in self.outcomes), Decimal("0")) - Decimal("1")) > Decimal("0.0001"):
            raise ValueError("mutually exclusive outcome probabilities must sum to one")


@dataclass(frozen=True)
class ProbabilityContext:
    model_version: str
    finish_probability: Decimal
    touch_probability: Decimal
    stop_probability: Decimal
    target_probability: Decimal


class ProbabilityModel:
    def estimate(self, context: ProbabilityContext) -> OutcomeDistribution:
        if not context.model_version:
            raise ValueError("probability model version is required")
        for value in (context.finish_probability, context.touch_probability, context.stop_probability, context.target_probability):
            if not Decimal("0") <= value <= Decimal("1"):
                raise ValueError("probability must be between zero and one")
        time_exit = Decimal("1") - context.stop_probability - context.target_probability
        if time_exit < 0:
            raise ValueError("stop and target probabilities cannot exceed one")
        outcomes = (
            Outcome("target", context.target_probability.quantize(Decimal("0.0001")), Decimal("0")),
            Outcome("stop", context.stop_probability.quantize(Decimal("0.0001")), Decimal("0")),
            Outcome("time_exit", time_exit.quantize(Decimal("0.0001")), Decimal("0")),
        )
        return OutcomeDistribution(
            outcomes, context.finish_probability, context.touch_probability,
            context.stop_probability, context.target_probability,
            (Decimal("1") - context.finish_probability), time_exit,
            context.model_version,
        )


def expected_net_value(outcomes: Sequence[Outcome], slippage: Decimal, fees: Decimal) -> Decimal:
    if abs(sum((item.probability for item in outcomes), Decimal("0")) - Decimal("1")) > Decimal("0.0001"):
        raise ValueError("outcome probabilities must sum to one")
    return sum((item.probability * item.net_pnl for item in outcomes), Decimal("0")) - slippage - fees
