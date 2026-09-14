import io
import json
from urllib.error import HTTPError

from option_bot.providers.http import JsonHttpTransport, PublicHttpClient


class Response:
    def __init__(self, status: int, payload: dict):
        self.status = status
        self._body = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_get_encodes_parameters_and_authenticates_without_putting_secrets_in_url() -> None:
    captured = {}

    def opener(request, timeout):
        captured.update(url=request.full_url, headers=dict(request.header_items()), timeout=timeout)
        return Response(200, {"snapshots": {}})

    transport = JsonHttpTransport(
        "https://data.alpaca.markets", "paper-key", "paper-secret", opener=opener
    )
    status, payload = transport("GET", "/v2/stocks/snapshots", {"symbols": "AAPL,MSFT"}, None)

    assert status == 200 and payload == {"snapshots": {}}
    assert captured["url"] == "https://data.alpaca.markets/v2/stocks/snapshots?symbols=AAPL%2CMSFT"
    assert "paper-key" not in captured["url"] and "paper-secret" not in captured["url"]
    assert captured["headers"]["Apca-api-key-id"] == "paper-key"
    assert captured["headers"]["Apca-api-secret-key"] == "paper-secret"


def test_http_error_returns_status_and_safe_json_payload() -> None:
    def opener(request, timeout):
        raise HTTPError(request.full_url, 403, "forbidden", {}, io.BytesIO(b'{"message":"forbidden"}'))

    transport = JsonHttpTransport(
        "https://data.alpaca.markets", "paper-key", "paper-secret", opener=opener
    )
    assert transport("GET", "/v2/stocks/snapshots", {}, None) == (403, {"message": "forbidden"})


def test_public_client_allows_only_read_only_https() -> None:
    captured = {}

    def opener(request, timeout):
        captured.update(method=request.method, url=request.full_url, headers=dict(request.header_items()))
        return Response(200, {"feed": []})

    client = PublicHttpClient(opener=opener)
    assert client.get_json("https://example.test/news") == {"feed": []}
    assert captured["method"] == "GET"
    assert captured["url"] == "https://example.test/news"
    assert captured["headers"]["User-agent"].startswith("Trade-Option-Bot/")

    try:
        client.get_bytes("http://example.test/news")
    except ValueError as exc:
        assert "HTTPS" in str(exc)
    else:
        raise AssertionError("non-HTTPS source was accepted")
