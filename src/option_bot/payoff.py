"""Exact expiration payoff calculations for defined-risk option structures."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from option_bot.domain import Money, OptionLeg, OptionRight, TradeSide


ZERO = Decimal("0")
CENT = Decimal("0.01")


def _signed_quantity(leg: OptionLeg) -> Decimal:
    sign = Decimal("1") if leg.side is TradeSide.BUY else Decimal("-1")
    return sign * Decimal(leg.quantity)


@dataclass(frozen=True)
class PayoffProfile:
    legs: tuple[OptionLeg, ...]
    net_credit: Money
    maximum_profit: Money
    maximum_loss: Money
    breakevens: tuple[Decimal, ...]
    multiplier: int

    @classmethod
    def evaluate(
        cls,
        legs: Sequence[OptionLeg],
        net_credit: Decimal,
        multiplier: int,
    ) -> "PayoffProfile":
        legs_tuple = tuple(legs)
        if len(legs_tuple) < 2:
            raise ValueError("a defined-risk structure requires at least two legs")
        if net_credit <= ZERO:
            raise ValueError("net credit must be positive")
        if multiplier <= 0:
            raise ValueError("multiplier must be positive")
        if len({leg.expiration for leg in legs_tuple}) != 1:
            raise ValueError("a defined-risk structure must use one expiration")

        high_slope = sum(
            (_signed_quantity(leg) for leg in legs_tuple if leg.right is OptionRight.CALL),
            ZERO,
        )
        if high_slope < ZERO:
            raise ValueError("structure does not have defined-risk upside")

        strikes = sorted({leg.strike for leg in legs_tuple})
        sample_prices = [ZERO, *strikes]
        unit_values = [cls._unit_pnl(legs_tuple, net_credit, price) for price in sample_prices]
        if high_slope > ZERO:
            raise ValueError("credit structure has unbounded profit and is unsupported")

        maximum = max(unit_values) * multiplier
        minimum = min(unit_values) * multiplier
        breakevens = cls._find_breakevens(legs_tuple, net_credit, sample_prices)
        return cls(
            legs=legs_tuple,
            net_credit=Money((net_credit * multiplier).quantize(CENT)),
            maximum_profit=Money(maximum.quantize(CENT)),
            maximum_loss=Money((-minimum).quantize(CENT)),
            breakevens=breakevens,
            multiplier=multiplier,
        )

    @staticmethod
    def _unit_pnl(legs: Sequence[OptionLeg], credit: Decimal, price: Decimal) -> Decimal:
        result = credit
        for leg in legs:
            if leg.right is OptionRight.CALL:
                intrinsic = max(price - leg.strike, ZERO)
            else:
                intrinsic = max(leg.strike - price, ZERO)
            result += _signed_quantity(leg) * intrinsic
        return result

    @classmethod
    def _find_breakevens(
        cls,
        legs: Sequence[OptionLeg],
        credit: Decimal,
        points: Sequence[Decimal],
    ) -> tuple[Decimal, ...]:
        roots: set[Decimal] = set()
        for left, right in zip(points, points[1:]):
            left_value = cls._unit_pnl(legs, credit, left)
            right_value = cls._unit_pnl(legs, credit, right)
            if left_value == ZERO:
                roots.add(left)
            if right_value == ZERO:
                roots.add(right)
            if left_value * right_value < ZERO:
                slope = (right_value - left_value) / (right - left)
                roots.add(left - (left_value / slope))
        return tuple(sorted(roots))

    def pnl_at(self, price: Decimal) -> Money:
        if price < ZERO:
            raise ValueError("underlying price cannot be negative")
        value = self._unit_pnl(self.legs, self.net_credit.amount / self.multiplier, price)
        return Money((value * self.multiplier).quantize(CENT))
