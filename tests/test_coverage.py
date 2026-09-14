from option_bot.coverage import build_coverage_report


SYMBOLS = ("AAPL", "XSP", "MRUT")


def test_coverage_reports_verified_contracts_and_fail_closed_reasons() -> None:
    calls = []

    def paper(method, path, params, body):
        calls.append(("paper", method, path, params))
        symbol = params["underlying_symbols"]
        if symbol == "MRUT":
            return 200, {"option_contracts": []}
        return 200, {
            "option_contracts": [{
                "symbol": f"{symbol}260914P00100000",
                "underlying_symbol": symbol,
                "expiration_date": "2026-09-14",
                "style": "american" if symbol == "AAPL" else "european",
                "settlement_type": "physical" if symbol == "AAPL" else "cash",
            }]
        }

    def market(method, path, params, body):
        calls.append(("market", method, path, params))
        if path.endswith("/XSP"):
            return 403, {"message": "subscription does not permit querying recent SIP data"}
        return 200, {"snapshots": {"contract": {"latestQuote": {"bp": 1, "ap": 2}}}}

    report = build_coverage_report(
        symbols=SYMBOLS,
        trade_date="2026-09-14",
        paper_transport=paper,
        market_transport=market,
    )

    assert report["paper_only"] is True and report["order_submission_enabled"] is False
    by_symbol = {row["symbol"]: row for row in report["symbols"]}
    assert by_symbol["AAPL"]["status"] == "AVAILABLE"
    assert by_symbol["AAPL"]["exercise_style"] == "AMERICAN"
    assert by_symbol["AAPL"]["settlement_type"] == "PHYSICAL"
    assert by_symbol["XSP"]["status"] == "DATA_UNAVAILABLE"
    assert by_symbol["XSP"]["reason_codes"] == ["OPTION_SNAPSHOT_HTTP_403"]
    assert by_symbol["MRUT"]["status"] == "NO_EXPIRATION_TODAY"
    assert not any(method != "GET" for _, method, _, _ in calls)


def test_coverage_does_not_invent_missing_product_metadata() -> None:
    def paper(*_):
        return 200, {"option_contracts": [{"symbol": "AAPL260914P00100000"}]}

    report = build_coverage_report(
        symbols=("AAPL",), trade_date="2026-09-14",
        paper_transport=paper, market_transport=lambda *_: (200, {"snapshots": {}}),
    )
    row = report["symbols"][0]
    assert row["status"] == "DATA_UNAVAILABLE"
    assert row["exercise_style"] is None and row["settlement_type"] is None
    assert "PRODUCT_METADATA_INCOMPLETE" in row["reason_codes"]


def test_coverage_reports_contract_provider_failure_without_snapshot_call() -> None:
    snapshot_calls = []
    report = build_coverage_report(
        symbols=("AAPL",), trade_date="2026-09-14",
        paper_transport=lambda *_: (429, {}),
        market_transport=lambda *args: snapshot_calls.append(args),
    )
    assert report["symbols"][0]["reason_codes"] == ["CONTRACTS_HTTP_429"]
    assert snapshot_calls == []


def test_invalid_underlying_is_reported_as_unsupported_without_substitution() -> None:
    snapshot_calls = []
    report = build_coverage_report(
        symbols=("MRUT",), trade_date="2026-09-14",
        paper_transport=lambda *_: (
            422,
            {"code": 42210000, "message": "invalid underlying symbols: MRUT"},
        ),
        market_transport=lambda *args: snapshot_calls.append(args),
    )
    row = report["symbols"][0]
    assert row["symbol"] == "MRUT"
    assert row["status"] == "UNSUPPORTED_UNDERLYING"
    assert row["reason_codes"] == ["ALPACA_INVALID_UNDERLYING"]
    assert snapshot_calls == []
