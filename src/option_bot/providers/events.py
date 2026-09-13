"""Aggregate event calendars and fail closed when none can be evaluated."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Mapping, Sequence

from option_bot.providers.base import Availability, EventGateEvidence


EventSource = Callable[[str, tuple[datetime, datetime]], Sequence[Mapping[str, Any]]]


class AggregatingEventProvider:
    def __init__(self, sources: Sequence[EventSource]):
        self._sources = tuple(sources)

    def get_event_gate(self, symbol: str, window: tuple[datetime, datetime]) -> EventGateEvidence:
        events: list[Mapping[str, Any]] = []
        succeeded = 0
        for source in self._sources:
            try:
                events.extend(source(symbol, window))
                succeeded += 1
            except (TimeoutError, ConnectionError, ValueError):
                continue
        if succeeded == 0:
            return EventGateEvidence(symbol, Availability.UNAVAILABLE, True, (), ("EVENT_SOURCES_UNAVAILABLE",))
        blocked = bool(events)
        return EventGateEvidence(symbol, Availability.AVAILABLE, blocked, tuple(events), ("BINARY_EVENT",) if blocked else ())
