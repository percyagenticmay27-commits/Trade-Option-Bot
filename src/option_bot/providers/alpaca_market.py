"""Alpaca market-data adapter with bounded retries for reads only."""

from __future__ import annotations

from datetime import datetime
from time import sleep
from typing import Any, Callable, Mapping, Sequence

from option_bot.providers.base import Availability, OptionSurface, SessionSnapshot
from option_bot.providers.normalization import normalize_option_surface, unavailable_surface


Transport = Callable[[str, str, Mapping[str, Any], Mapping[str, Any] | None], tuple[int, Mapping[str, Any]]]


class AlpacaMarketDataClient:
    def __init__(self, transport: Transport, max_read_attempts: int = 3, sleeper: Callable[[float], None] = sleep):
        if max_read_attempts < 1:
            raise ValueError("max_read_attempts must be positive")
        self._transport = transport
        self._attempts = max_read_attempts
        self._sleep = sleeper

    def _read(self, path: str, params: Mapping[str, Any]) -> tuple[int, Mapping[str, Any]]:
        last_status = 0
        last_payload: Mapping[str, Any] = {}
        for attempt in range(self._attempts):
            try:
                last_status, last_payload = self._transport("GET", path, params, None)
            except TimeoutError:
                if attempt + 1 == self._attempts:
                    raise
                self._sleep(0.25 * (2 ** attempt))
                continue
            if last_status not in (429,) and last_status < 500:
                return last_status, last_payload
            if attempt + 1 < self._attempts:
                self._sleep(0.25 * (2 ** attempt))
        return last_status, last_payload

    def get_option_surface(self, symbol: str, expiration: str, as_of: datetime) -> OptionSurface:
        if not expiration:
            return unavailable_surface(symbol, expiration, "EXPIRATION_REQUIRED")
        try:
            status, payload = self._read("/v1beta1/options/snapshots/" + symbol, {"expiration_date": expiration})
        except TimeoutError:
            return unavailable_surface(symbol, expiration, "PROVIDER_TIMEOUT")
        if status == 429:
            return unavailable_surface(symbol, expiration, "RATE_LIMITED", status=status)
        if status >= 400:
            return unavailable_surface(symbol, expiration, "PROVIDER_ERROR", status=status)
        return normalize_option_surface(symbol, expiration, payload, as_of)

    def get_session_snapshot(self, symbols: Sequence[str], as_of: datetime) -> SessionSnapshot:
        try:
            status, payload = self._read("/v2/stocks/snapshots", {"symbols": ",".join(symbols)})
        except TimeoutError:
            return SessionSnapshot(tuple(symbols), as_of, {}, Availability.UNAVAILABLE, ("PROVIDER_TIMEOUT",))
        if status >= 400:
            reason = "RATE_LIMITED" if status == 429 else "PROVIDER_ERROR"
            return SessionSnapshot(tuple(symbols), as_of, payload, Availability.UNAVAILABLE, (reason,))
        return SessionSnapshot(tuple(symbols), as_of, payload, Availability.AVAILABLE)
