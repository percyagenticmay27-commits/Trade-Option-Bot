"""Read-only governed-symbol product and same-day-expiration coverage."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from option_bot.product_registry import product_metadata


Transport = Callable[
    [str, str, Mapping[str, Any], Mapping[str, Any] | None],
    tuple[int, Mapping[str, Any]],
]


def _contracts(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = payload.get("option_contracts", payload.get("contracts", []))
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _metadata(contract: Mapping[str, Any], field: str) -> str | None:
    value = contract.get(field)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().upper()


def build_coverage_report(
    *,
    symbols: Sequence[str],
    trade_date: str,
    paper_transport: Transport,
    market_transport: Transport,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        status, payload = paper_transport(
            "GET",
            "/v2/options/contracts",
            {
                "underlying_symbols": symbol,
                "expiration_date": trade_date,
                "status": "active",
                "limit": 10000,
            },
            None,
        )
        base = {
            "symbol": symbol,
            "trade_date": trade_date,
            "contract_count": 0,
            "exercise_style": None,
            "settlement_type": None,
            "product_type": None,
            "provider_reported_exercise_style": None,
            "provider_reported_settlement_type": None,
            "settlement_source": None,
            "metadata_source_url": None,
            "status": "DATA_UNAVAILABLE",
            "reason_codes": [],
        }
        if status != 200:
            message = str(payload.get("message") or "").lower()
            if status == 422 and "invalid underlying" in message:
                rows.append({
                    **base,
                    "status": "UNSUPPORTED_UNDERLYING",
                    "reason_codes": ["ALPACA_INVALID_UNDERLYING"],
                })
                continue
            rows.append({**base, "reason_codes": [f"CONTRACTS_HTTP_{status}"]})
            continue
        contracts = _contracts(payload)
        if not contracts:
            rows.append({**base, "status": "NO_EXPIRATION_TODAY", "reason_codes": ["NO_ACTIVE_CONTRACTS"]})
            continue
        style = _metadata(contracts[0], "style")
        provider_settlement = _metadata(contracts[0], "settlement_type")
        reference = product_metadata(symbol)
        reference_style = reference.get("exercise_style") if reference else None
        settlement = provider_settlement or (reference.get("settlement_type") if reference else None)
        product = {
            **base,
            "contract_count": len(contracts),
            "exercise_style": style,
            "settlement_type": settlement,
            "product_type": reference.get("product_type") if reference else None,
            "provider_reported_exercise_style": style,
            "provider_reported_settlement_type": provider_settlement,
            "settlement_source": (
                "ALPACA_CONTRACT" if provider_settlement else
                (reference.get("metadata_source") if reference else None)
            ),
            "metadata_source_url": reference.get("source_url") if reference else None,
        }
        if reference_style and style and reference_style != style:
            rows.append({**product, "reason_codes": ["EXERCISE_STYLE_CONFLICT"]})
            continue
        if style is None or settlement is None or product["product_type"] is None:
            rows.append({**product, "reason_codes": ["PRODUCT_METADATA_INCOMPLETE"]})
            continue
        quote_status, _ = market_transport(
            "GET",
            f"/v1beta1/options/snapshots/{symbol}",
            {"expiration_date": trade_date, "feed": "indicative", "limit": 1000},
            None,
        )
        if quote_status != 200:
            rows.append({**product, "reason_codes": [f"OPTION_SNAPSHOT_HTTP_{quote_status}"]})
            continue
        rows.append({**product, "status": "AVAILABLE", "reason_codes": []})
    return {
        "module_id": "OPTION-001",
        "strategy_type": "0DTE_OPTIONS",
        "trade_date": trade_date,
        "paper_only": True,
        "order_submission_enabled": False,
        "symbols": rows,
    }
