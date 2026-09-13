"""Typed, fail-closed provider contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence

from option_bot.domain import PaperMultiLegOrder, PaperOrderResult, ProductMetadata


class Availability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class NormalizedOptionContract:
    symbol: str
    bid: str
    ask: str
    bid_size: int
    ask_size: int
    delta: str
    gamma: str
    theta: str
    vega: str
    iv: str
    volume: int
    open_interest: int
    source_time: datetime
    received_time: datetime
    product: ProductMetadata


@dataclass(frozen=True)
class OptionSurface:
    symbol: str
    expiration: str
    contracts: tuple[NormalizedOptionContract, ...]
    feed: str
    availability: Availability
    reason_codes: tuple[str, ...] = ()
    evidence: Mapping[str, str] | None = None


@dataclass(frozen=True)
class SessionSnapshot:
    symbols: tuple[str, ...]
    as_of: datetime
    payload: Mapping[str, Any]
    availability: Availability
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class EventGateEvidence:
    symbol: str
    availability: Availability
    blocked: bool
    events: tuple[Mapping[str, Any], ...]
    reason_codes: tuple[str, ...] = ()


class MarketDataProvider(Protocol):
    def get_session_snapshot(self, symbols: Sequence[str], as_of: datetime) -> SessionSnapshot: ...
    def get_option_surface(self, symbol: str, expiration: str, as_of: datetime) -> OptionSurface: ...


class PaperBroker(Protocol):
    def submit_multileg(self, order: PaperMultiLegOrder) -> PaperOrderResult: ...
    def cancel(self, order_id: str) -> PaperOrderResult: ...


class EventProvider(Protocol):
    def get_event_gate(self, symbol: str, window: tuple[datetime, datetime]) -> EventGateEvidence: ...
