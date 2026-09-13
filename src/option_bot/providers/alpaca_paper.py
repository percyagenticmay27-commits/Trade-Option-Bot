"""Paper-only Alpaca order adapter; submissions are deliberately never retried."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

from option_bot.config import PAPER_BASE_URL
from option_bot.domain import PaperMultiLegOrder, PaperOrderResult


ET = ZoneInfo("America/New_York")
Transport = Callable[[str, str, Mapping[str, Any], Mapping[str, Any] | None], tuple[int, Mapping[str, Any]]]


class AlpacaPaperClient:
    def __init__(self, base_url: str, transport: Transport):
        if base_url != PAPER_BASE_URL:
            raise ValueError(f"paper endpoint must be exactly {PAPER_BASE_URL}")
        self._transport = transport

    def submit_multileg(self, order: PaperMultiLegOrder) -> PaperOrderResult:
        body = {
            "client_order_id": order.order_id,
            "order_class": "mleg",
            "qty": "1",
            "type": "limit",
            "time_in_force": "day",
            "limit_price": str(order.limit_credit.amount),
            "legs": [
                {"symbol": leg.contract_symbol, "ratio_qty": str(leg.quantity), "side": leg.side.value.lower(), "position_intent": "sell_to_open" if leg.side.value == "SELL" else "buy_to_open"}
                for leg in order.candidate.legs
            ],
        }
        try:
            status, payload = self._transport("POST", "/v2/orders", {}, body)
        except TimeoutError:
            return PaperOrderResult(order.order_id, "UNKNOWN", datetime.now(ET), "submission outcome requires reconciliation")
        remote_id = str(payload.get("id", order.order_id))
        result_status = str(payload.get("status", "REJECTED" if status >= 400 else "accepted"))
        return PaperOrderResult(remote_id, result_status, datetime.now(ET), str(payload.get("message", "")))

    def cancel(self, order_id: str) -> PaperOrderResult:
        try:
            status, payload = self._transport("DELETE", f"/v2/orders/{order_id}", {}, None)
        except TimeoutError:
            return PaperOrderResult(order_id, "UNKNOWN", datetime.now(ET), "cancel outcome requires reconciliation")
        result = "CANCELED" if status in (200, 204) else str(payload.get("status", "REJECTED"))
        return PaperOrderResult(order_id, result, datetime.now(ET), str(payload.get("message", "")))
