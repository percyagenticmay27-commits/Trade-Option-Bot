"""Authenticated JSON HTTP transport boundary."""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class JsonHttpTransport:
    def __init__(
        self,
        base_url: str,
        key_id: str,
        secret_key: str,
        *,
        opener: Callable[..., Any] = urlopen,
        timeout: float = 10.0,
    ) -> None:
        if not base_url.startswith("https://"):
            raise ValueError("provider base URL must use HTTPS")
        self._base_url = base_url.rstrip("/")
        self._key_id = key_id
        self._secret_key = secret_key
        self._opener = opener
        self._timeout = timeout

    @staticmethod
    def _payload(raw: bytes) -> Mapping[str, Any]:
        if not raw:
            return {}
        value = json.loads(raw.decode("utf-8"))
        return value if isinstance(value, Mapping) else {"data": value}

    def __call__(
        self,
        method: str,
        path: str,
        params: Mapping[str, Any],
        body: Mapping[str, Any] | None,
    ) -> tuple[int, Mapping[str, Any]]:
        query = urlencode(params) if params else ""
        url = f"{self._base_url}{path}" + (f"?{query}" if query else "")
        encoded = json.dumps(dict(body)).encode("utf-8") if body is not None else None
        request = Request(
            url,
            data=encoded,
            method=method,
            headers={
                "APCA-API-KEY-ID": self._key_id,
                "APCA-API-SECRET-KEY": self._secret_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            with self._opener(request, timeout=self._timeout) as response:
                return int(response.status), self._payload(response.read())
        except HTTPError as exc:
            return int(exc.code), self._payload(exc.read())


def build_json_transport(base_url: str, key_id: str, secret_key: str) -> JsonHttpTransport:
    return JsonHttpTransport(base_url, key_id, secret_key)


class PublicHttpClient:
    """Small read-only client for public JSON and RSS sources."""

    def __init__(self, *, opener: Callable[..., Any] = urlopen, timeout: float = 10.0) -> None:
        self._opener = opener
        self._timeout = timeout

    def get_bytes(self, url: str) -> bytes:
        if not url.startswith("https://"):
            raise ValueError("public provider URL must use HTTPS")
        request = Request(
            url,
            method="GET",
            headers={
                "Accept": "application/json, application/rss+xml, text/calendar, text/html",
                "User-Agent": "Trade-Option-Bot/0.1 read-only event monitor",
            },
        )
        with self._opener(request, timeout=self._timeout) as response:
            return response.read()

    def get_json(self, url: str) -> Mapping[str, Any]:
        return JsonHttpTransport._payload(self.get_bytes(url))
