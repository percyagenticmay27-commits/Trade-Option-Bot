"""Immutable contracts shared by the option module's bounded components."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Mapping


class OperatingMode(str, Enum):
    PAPER = "PAPER"


class StrategyType(str, Enum):
    ODTE_OPTIONS = "0DTE_OPTIONS"
    WHEEL_OPTIONS = "WHEEL_OPTIONS"


class Decision(str, Enum):
    TRADE = "TRADE"
    WATCH = "WATCH"
    NO_TRADE = "NO_TRADE"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


class StructureType(str, Enum):
    PUT_CREDIT_SPREAD = "PUT_CREDIT_SPREAD"
    CALL_CREDIT_SPREAD = "CALL_CREDIT_SPREAD"
    IRON_CONDOR = "IRON_CONDOR"
    IRON_BUTTERFLY = "IRON_BUTTERFLY"


class LifecycleStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    ORDER_PENDING = "ORDER_PENDING"
    OPEN = "OPEN"
    DEGRADED = "DEGRADED"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"


class OptionRight(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


class TradeSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class ExerciseStyle(str, Enum):
    AMERICAN = "AMERICAN"
    EUROPEAN = "EUROPEAN"


class SettlementType(str, Enum):
    PHYSICAL = "PHYSICAL"
    CASH = "CASH"


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str = "USD"

    def __post_init__(self) -> None:
        if not self.currency or len(self.currency) != 3:
            raise ValueError("currency must be a three-letter code")


@dataclass(frozen=True)
class EvidenceTimestamp:
    source_time: datetime
    received_time: datetime

    def __post_init__(self) -> None:
        if self.source_time.tzinfo is None or self.received_time.tzinfo is None:
            raise ValueError("evidence timestamps must be timezone-aware")


@dataclass(frozen=True)
class ProductMetadata:
    symbol: str
    multiplier: int
    exercise_style: ExerciseStyle
    settlement_type: SettlementType
    last_trading_time: str

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("product symbol is required")
        if self.multiplier <= 0:
            raise ValueError("product multiplier must be positive")
        hour, minute = self.last_trading_time.split(":", maxsplit=1)
        if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
            raise ValueError("last_trading_time must be HH:MM")


@dataclass(frozen=True)
class OptionLeg:
    contract_symbol: str
    right: OptionRight
    side: TradeSide
    strike: Decimal
    expiration: str
    quantity: int

    def __post_init__(self) -> None:
        if not self.contract_symbol:
            raise ValueError("contract symbol is required")
        if self.strike <= 0:
            raise ValueError("strike must be positive")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")


@dataclass(frozen=True)
class OptionQuote:
    contract_symbol: str
    bid: Decimal
    ask: Decimal
    timestamp: EvidenceTimestamp
    bid_size: int = 0
    ask_size: int = 0

    def __post_init__(self) -> None:
        if self.bid < 0 or self.ask < 0:
            raise ValueError("quote prices cannot be negative")
        if self.ask < self.bid:
            raise ValueError("option quote cannot be crossed")


@dataclass(frozen=True)
class TradeCandidate:
    candidate_id: str
    underlying_symbol: str
    legs: tuple[OptionLeg, ...]
    product: ProductMetadata
    net_credit: Money | None = None
    operating_mode: OperatingMode = OperatingMode.PAPER

    def __post_init__(self) -> None:
        if not self.candidate_id or not self.underlying_symbol:
            raise ValueError("candidate identity is required")
        if len(self.legs) < 2:
            raise ValueError("a defined-risk candidate requires at least two legs")
        expirations = {leg.expiration for leg in self.legs}
        if len(expirations) != 1:
            raise ValueError("all option legs must use the same expiration")
        if self.product.symbol != self.underlying_symbol:
            raise ValueError("candidate product must match underlying")
        if self.net_credit is not None and self.net_credit.amount <= 0:
            raise ValueError("candidate net credit must be positive")


@dataclass(frozen=True)
class PortfolioRiskState:
    trade_date: str
    entry_count: int
    defined_loss: Money

    def __post_init__(self) -> None:
        if self.entry_count < 0 or self.defined_loss.amount < 0:
            raise ValueError("portfolio risk state cannot be negative")


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    reason_codes: tuple[str, ...]
    evidence: Mapping[str, str]

    def __post_init__(self) -> None:
        if self.allowed and self.reason_codes:
            raise ValueError("allowed gate decision cannot contain rejection reasons")
        if not self.allowed and not self.reason_codes:
            raise ValueError("rejected gate decision requires a reason")


@dataclass(frozen=True)
class PaperMultiLegOrder:
    order_id: str
    candidate: TradeCandidate
    limit_credit: Money
    submitted_at: datetime

    def __post_init__(self) -> None:
        if self.submitted_at.tzinfo is None:
            raise ValueError("order timestamp must be timezone-aware")
        if self.limit_credit.amount <= 0:
            raise ValueError("credit order must request a positive credit")


@dataclass(frozen=True)
class PaperOrderResult:
    order_id: str
    status: str
    observed_at: datetime
    message: str = ""

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None:
            raise ValueError("order result timestamp must be timezone-aware")


@dataclass(frozen=True)
class Position:
    position_id: str
    candidate: TradeCandidate
    opened_at: datetime
    status: LifecycleStatus = LifecycleStatus.OPEN

    def __post_init__(self) -> None:
        if self.opened_at.tzinfo is None:
            raise ValueError("position timestamp must be timezone-aware")


@dataclass(frozen=True)
class PositionAction:
    position_id: str
    action: str
    reason_code: str
    observed_at: datetime

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None:
            raise ValueError("position action timestamp must be timezone-aware")
