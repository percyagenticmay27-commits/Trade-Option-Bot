"""Enumerate governed 0DTE structures across the complete delta ladder."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from option_bot.domain import Money, OptionLeg, OptionRight, StructureType, TradeCandidate, TradeSide
from option_bot.evidence import EvidenceBundle
from option_bot.payoff import PayoffProfile
from option_bot.providers.base import Availability, NormalizedOptionContract, OptionSurface


BASE_DELTAS = tuple(Decimal(value) for value in ("0.08", "0.10", "0.12", "0.15", "0.18", "0.20"))


@dataclass(frozen=True)
class StructureConfig:
    bias: str
    support: Decimal
    resistance: Decimal
    expected_lower: Decimal
    expected_upper: Decimal
    max_loss: Decimal
    allow_delta_25: bool = False
    landing_zone: Decimal | None = None
    delta_tolerance: Decimal = Decimal("0.025")
    max_gamma: Decimal = Decimal("0.20")
    min_size: int = 1
    max_relative_spread: Decimal = Decimal("0.50")


@dataclass(frozen=True)
class StructureAttempt:
    target_delta: Decimal
    accepted: bool
    reason_codes: frozenset[str]
    candidate: TradeCandidate | None = None


@dataclass(frozen=True)
class StructureGeneration:
    attempts: tuple[StructureAttempt, ...]
    butterfly_body: Decimal | None = None

    @property
    def candidates(self) -> tuple[TradeCandidate, ...]:
        return tuple(item.candidate for item in self.attempts if item.candidate is not None)


def _mid(contract: NormalizedOptionContract) -> Decimal:
    return (Decimal(contract.bid) + Decimal(contract.ask)) / 2


def _nearest(contracts, target):
    return min(contracts, key=lambda item: abs(abs(Decimal(item.delta)) - target), default=None)


def _leg(contract, side):
    return OptionLeg(contract.symbol, OptionRight(contract.right), side, Decimal(contract.strike), contract.expiration, 1)


def _quality_reasons(contract: NormalizedOptionContract, config: StructureConfig) -> set[str]:
    reasons = set()
    bid, ask = Decimal(contract.bid), Decimal(contract.ask)
    midpoint = (bid + ask) / 2
    if contract.bid_size < config.min_size or contract.ask_size < config.min_size or midpoint <= 0 or (ask - bid) / midpoint > config.max_relative_spread:
        reasons.add("LIQUIDITY_REJECTED")
    if abs(Decimal(contract.gamma)) > config.max_gamma:
        reasons.add("GAMMA_REJECTED")
    return reasons


class StructureGenerator:
    @staticmethod
    def generate(surface: OptionSurface, evidence: EvidenceBundle, config: StructureConfig) -> StructureGeneration:
        del evidence
        deltas = BASE_DELTAS + ((Decimal("0.25"),) if config.allow_delta_25 else ())
        if surface.availability is not Availability.AVAILABLE:
            return StructureGeneration(tuple(StructureAttempt(delta, False, frozenset({"SURFACE_UNAVAILABLE"})) for delta in deltas), config.landing_zone)
        puts = [item for item in surface.contracts if item.right == "PUT"]
        calls = [item for item in surface.contracts if item.right == "CALL"]
        attempts = []
        for target in deltas:
            if config.bias == "BEARISH":
                short = _nearest(calls, target)
                wings = [item for item in calls if short and Decimal(item.strike) > Decimal(short.strike)]
                structure = StructureType.CALL_CREDIT_SPREAD
            elif config.bias == "NEUTRAL":
                short_put, short_call = _nearest(puts, target), _nearest(calls, target)
                put_wings = [item for item in puts if short_put and Decimal(item.strike) < Decimal(short_put.strike)]
                call_wings = [item for item in calls if short_call and Decimal(item.strike) > Decimal(short_call.strike)]
                short = short_put
                wings = put_wings
                structure = StructureType.IRON_CONDOR
            else:
                short = _nearest(puts, target)
                wings = [item for item in puts if short and Decimal(item.strike) < Decimal(short.strike)]
                structure = StructureType.PUT_CREDIT_SPREAD
            reasons: set[str] = set()
            if short is None or abs(abs(Decimal(short.delta)) - target) > config.delta_tolerance:
                attempts.append(StructureAttempt(target, False, frozenset({"NO_NEAR_DELTA_CONTRACT"})))
                continue
            reasons |= _quality_reasons(short, config)
            strike = Decimal(short.strike)
            if structure is StructureType.PUT_CREDIT_SPREAD and (strike >= config.support or strike >= config.expected_lower):
                reasons.add("TECHNICAL_CLEARANCE_REJECTED")
            if structure is StructureType.CALL_CREDIT_SPREAD and (strike <= config.resistance or strike <= config.expected_upper):
                reasons.add("TECHNICAL_CLEARANCE_REJECTED")
            if not wings:
                reasons.add("PROTECTIVE_WING_UNAVAILABLE")
                attempts.append(StructureAttempt(target, False, frozenset(reasons)))
                continue
            wing = max(wings, key=lambda item: Decimal(item.strike)) if structure is StructureType.PUT_CREDIT_SPREAD else min(wings, key=lambda item: Decimal(item.strike))
            reasons |= _quality_reasons(wing, config)
            legs = (_leg(short, TradeSide.SELL), _leg(wing, TradeSide.BUY))
            credit = Decimal(short.bid) - Decimal(wing.ask)
            if structure is StructureType.IRON_CONDOR:
                short_call = _nearest(calls, target)
                call_wings = [item for item in calls if short_call and Decimal(item.strike) > Decimal(short_call.strike)]
                if short_call is None or not call_wings:
                    reasons.add("PROTECTIVE_WING_UNAVAILABLE")
                else:
                    call_wing = min(call_wings, key=lambda item: Decimal(item.strike))
                    reasons |= _quality_reasons(short_call, config) | _quality_reasons(call_wing, config)
                    legs += (_leg(short_call, TradeSide.SELL), _leg(call_wing, TradeSide.BUY))
                    credit += Decimal(short_call.bid) - Decimal(call_wing.ask)
            candidate = None
            if credit <= 0:
                reasons.add("INSUFFICIENT_CREDIT")
            else:
                try:
                    profile = PayoffProfile.evaluate(legs, credit, surface.contracts[0].product.multiplier)
                    if profile.maximum_loss.amount > config.max_loss:
                        reasons.add("MAX_LOSS_LIMIT")
                    if not reasons:
                        candidate = TradeCandidate(f"{surface.symbol}-{structure.value}-{target}", surface.symbol, legs, surface.contracts[0].product, Money(credit), structure_type=structure)
                except ValueError:
                    reasons.add("INVALID_PAYOFF")
            attempts.append(StructureAttempt(target, not reasons, frozenset(reasons), candidate))
        return StructureGeneration(tuple(attempts), config.landing_zone)
