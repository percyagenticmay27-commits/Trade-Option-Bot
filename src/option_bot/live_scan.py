"""Composition and report contracts for evidence-backed OPTION-001 scans."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

from option_bot.domain import Decision, TradeCandidate
from option_bot.evidence import EvidenceBundle
from option_bot.indicators import Bar, IndicatorEngine, IndicatorSnapshot
from option_bot.payoff import PayoffProfile
from option_bot.portfolio import PortfolioSelector, SelectableCandidate
from option_bot.providers.base import Availability, EventGateEvidence, OptionSurface
from option_bot.providers.normalization import normalize_option_surface
from option_bot.reporting import ReportBundle
from option_bot.structures import StructureConfig, StructureGenerator


ET = ZoneInfo("America/New_York")
Transport = Callable[[str, str, Mapping[str, Any], Mapping[str, Any] | None], tuple[int, Mapping[str, Any]]]


@dataclass(frozen=True)
class EvaluatedSetup:
    symbol: str
    decision: Decision
    candidate: SelectableCandidate | None
    direction_score: int | None
    range_score: int | None
    premium_score: int | None
    expected_value: Decimal | None
    reason_codes: tuple[str, ...]
    evidence_id: str

    @classmethod
    def unavailable(cls, symbol: str, reasons: tuple[str, ...]) -> "EvaluatedSetup":
        return cls(symbol, Decision.DATA_UNAVAILABLE, None, None, None, None, None, reasons, f"unavailable:{symbol}")


class SetupEvaluator:
    """Turn normalized provider evidence into an auditable setup decision."""

    def __init__(
        self, *, score: Callable[[IndicatorSnapshot, OptionSurface, EventGateEvidence], EvidenceBundle],
        generate: Callable[[OptionSurface, EvidenceBundle, object], Sequence[TradeCandidate]],
        trade_threshold: int, watch_threshold: int, max_loss: Decimal,
    ):
        self._score = score
        self._generate = generate
        self._trade_threshold = trade_threshold
        self._watch_threshold = watch_threshold
        self._max_loss = max_loss

    def evaluate(
        self, symbol: str, indicators: IndicatorSnapshot, surface: OptionSurface,
        events: EventGateEvidence, structure_config: object | None = None,
    ) -> EvaluatedSetup:
        evidence = self._score(indicators, surface, events)
        evidence_id = f"{evidence.model_hash}:{symbol}"
        if not evidence.available:
            return EvaluatedSetup.unavailable(symbol, evidence.reason_codes)
        generated = self._generate(surface, evidence, structure_config)
        candidates = tuple(generated.candidates) if hasattr(generated, "candidates") else tuple(generated)
        scored: list[tuple[Decimal, Decimal, TradeCandidate]] = []
        for candidate in candidates:
            if candidate.net_credit is None or candidate.structure_type is None:
                continue
            payoff = PayoffProfile.evaluate(candidate.legs, candidate.net_credit.amount, candidate.product.multiplier)
            if payoff.maximum_loss.amount <= self._max_loss:
                rank = Decimal(max(evidence.direction_score, evidence.range_score)) + Decimal(evidence.premium_score) / Decimal(10)
                expected = (payoff.maximum_profit.amount * Decimal("0.80")) - (payoff.maximum_loss.amount * Decimal("0.20"))
                scored.append((rank, expected, candidate))
        if not scored:
            reasons = {"NO_VALID_STRUCTURE"}
            if hasattr(generated, "attempts"):
                for attempt in generated.attempts:
                    reasons.update(attempt.reason_codes)
            decision = Decision.WATCH if max(evidence.direction_score, evidence.range_score) >= self._watch_threshold else Decision.NO_TRADE
            return EvaluatedSetup(symbol, decision, None, evidence.direction_score, evidence.range_score, evidence.premium_score, None, tuple(sorted(reasons)), evidence_id)
        rank, expected, candidate = max(scored, key=lambda row: (row[0], row[1]))
        decision = Decision.TRADE if max(evidence.direction_score, evidence.range_score) >= self._trade_threshold and expected > 0 else Decision.WATCH
        selectable = SelectableCandidate(symbol, candidate.candidate_id, candidate.structure_type, rank, PayoffProfile.evaluate(candidate.legs, candidate.net_credit.amount, candidate.product.multiplier).maximum_loss.amount, _exposure_group(symbol))
        reasons = () if decision is Decision.TRADE else ("SCORE_BELOW_THRESHOLD",)
        return EvaluatedSetup(symbol, decision, selectable, evidence.direction_score, evidence.range_score, evidence.premium_score, expected, reasons, evidence_id)


def _exposure_group(symbol: str) -> str:
    if symbol in {"NVDA", "GOOGL", "AAPL", "MSFT", "AMZN", "META", "AVGO"}:
        return "MEGA_CAP_TECH"
    if symbol in {"XSP", "DJX", "MRUT"}:
        return "US_INDEX"
    return symbol


def _bars(payload: Mapping[str, Any]) -> tuple[Bar, ...]:
    raw = payload.get("bars", ())
    if isinstance(raw, Mapping):
        raw = next(iter(raw.values()), ())
    result = []
    for item in raw if isinstance(raw, list) else ():
        try:
            stamp = datetime.fromisoformat(str(item.get("t", item.get("timestamp"))).replace("Z", "+00:00")).astimezone(ET)
            result.append(Bar(stamp, Decimal(str(item.get("o", item.get("open")))), Decimal(str(item.get("h", item.get("high")))), Decimal(str(item.get("l", item.get("low")))), Decimal(str(item.get("c", item.get("close")))), int(item.get("v", item.get("volume")))))
        except (AttributeError, TypeError, ValueError):
            continue
    return tuple(sorted(result, key=lambda bar: bar.timestamp))


def _aggregate_15m(bars: Sequence[Bar]) -> tuple[Bar, ...]:
    buckets: dict[datetime, list[Bar]] = {}
    for bar in bars:
        minute = (bar.timestamp.minute // 15) * 15
        key = bar.timestamp.replace(minute=minute, second=0, microsecond=0)
        buckets.setdefault(key, []).append(bar)
    return tuple(Bar(key, rows[0].open, max(row.high for row in rows), min(row.low for row in rows), rows[-1].close, sum(row.volume for row in rows)) for key, rows in sorted(buckets.items()))


def _combined_chain(contracts_payload: Mapping[str, Any], snapshots_payload: Mapping[str, Any]) -> dict[str, Any]:
    contracts = contracts_payload.get("option_contracts", contracts_payload.get("contracts", ()))
    metadata = {str(row.get("symbol")): row for row in contracts if isinstance(row, Mapping)} if isinstance(contracts, list) else {}
    snapshots = snapshots_payload.get("snapshots", snapshots_payload.get("contracts", snapshots_payload.get("chain", {})))
    combined: dict[str, dict[str, Any]] = {}
    for symbol, snapshot in snapshots.items() if isinstance(snapshots, Mapping) else ():
        if not isinstance(snapshot, Mapping):
            continue
        contract = dict(metadata.get(str(symbol), {}))
        quote = snapshot.get("latestQuote", snapshot.get("latest_quote", {}))
        greeks = snapshot.get("greeks") or {}
        contract.update({
            "symbol": symbol, "latest_quote": {
                "bid_price": quote.get("bp", quote.get("bid_price")), "ask_price": quote.get("ap", quote.get("ask_price")),
                "bid_size": quote.get("bs", quote.get("bid_size", 0)), "ask_size": quote.get("as", quote.get("ask_size", 0)),
                "timestamp": quote.get("t", quote.get("timestamp")),
            },
            "greeks": {"delta": greeks.get("delta"), "gamma": greeks.get("gamma"), "theta": greeks.get("theta"), "vega": greeks.get("vega")},
            "implied_volatility": snapshot.get("impliedVolatility", snapshot.get("implied_volatility")),
        })
        combined[str(symbol)] = contract
    return {"contracts": combined, "feed": "indicative"}


def evaluate_live_scan(
    *, symbols: Sequence[str], trade_date: str, as_of: datetime, paper_transport: Transport,
    market_transport: Transport, event_report: Mapping[str, Any], evidence_engine: object,
    max_loss: Decimal, trade_threshold: int, watch_threshold: int,
) -> tuple[EvaluatedSetup, ...]:
    """Read Alpaca evidence and evaluate every governed symbol without submitting orders."""
    if as_of.tzinfo is None:
        raise ValueError("scan time must be timezone-aware")
    start = as_of.astimezone(ET).replace(hour=4, minute=0, second=0, microsecond=0)
    event_rows = {row.get("symbol"): row for row in event_report.get("symbols", ()) if isinstance(row, Mapping)}
    scheduled_available = event_report.get("scheduled_calendar_status") == "AVAILABLE"
    evaluator = SetupEvaluator(
        score=evidence_engine.score, generate=StructureGenerator.generate,
        trade_threshold=trade_threshold, watch_threshold=watch_threshold, max_loss=max_loss,
    )
    results = []
    for symbol in symbols:
        contract_status, contract_payload = paper_transport("GET", "/v2/options/contracts", {"underlying_symbols": symbol, "expiration_date": trade_date, "status": "active", "limit": 10000}, None)
        if contract_status != 200:
            results.append(EvaluatedSetup.unavailable(symbol, (f"CONTRACTS_HTTP_{contract_status}",)))
            continue
        contracts = contract_payload.get("option_contracts", contract_payload.get("contracts", ()))
        if not contracts:
            results.append(EvaluatedSetup(symbol, Decision.NO_TRADE, None, None, None, None, None, ("NO_EXPIRATION_TODAY",), f"{trade_date}:{symbol}"))
            continue
        snapshot_status, snapshot_payload = market_transport("GET", f"/v1beta1/options/snapshots/{symbol}", {"expiration_date": trade_date, "feed": "indicative", "limit": 1000}, None)
        if snapshot_status != 200:
            results.append(EvaluatedSetup.unavailable(symbol, (f"OPTION_SNAPSHOT_HTTP_{snapshot_status}",)))
            continue
        surface = normalize_option_surface(symbol, trade_date, _combined_chain(contract_payload, snapshot_payload), as_of)
        bars_status, bars_payload = market_transport("GET", f"/v2/stocks/{symbol}/bars", {"timeframe": "5Min", "start": start.isoformat(), "end": as_of.isoformat(), "feed": "iex", "adjustment": "raw", "limit": 1000}, None)
        bars = _bars(bars_payload) if bars_status == 200 else ()
        if len(bars) < 20:
            indicators = IndicatorEngine.compute(bars, (), {})
        else:
            average_volume = sum(row.volume for row in bars[:-1]) / max(1, len(bars) - 1)
            indicators = IndicatorEngine.compute(bars, _aggregate_15m(bars), {"average_volume": average_volume, "previous_high": max(row.high for row in bars), "previous_low": min(row.low for row in bars)})
        event_row = event_rows.get(symbol, {})
        events = EventGateEvidence(symbol, Availability.AVAILABLE if scheduled_available else Availability.UNAVAILABLE, event_report.get("event_gate") != "CLEAR" or event_row.get("headline_gate") == "BLOCKED", tuple(event_report.get("scheduled_events", ())), tuple(event_report.get("reason_codes", ())) + tuple(event_row.get("reason_codes", ())))
        if not indicators.available or surface.availability is not Availability.AVAILABLE:
            reasons = indicators.reason_codes + surface.reason_codes
            results.append(EvaluatedSetup.unavailable(symbol, reasons))
            continue
        bias = "NEUTRAL" if indicators.adx14 <= 20 and indicators.chop14 >= 55 else ("BULLISH" if indicators.price >= indicators.vwap else "BEARISH")
        config = StructureConfig(bias, min(indicators.opening_range_low, indicators.previous_low), max(indicators.opening_range_high, indicators.previous_high), indicators.price - Decimal(str(indicators.atr14)), indicators.price + Decimal(str(indicators.atr14)), max_loss)
        results.append(evaluator.evaluate(symbol, indicators, surface, events, config))
    return tuple(results)


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_scan_report(
    *, trade_date: str, symbols: Sequence[str], evaluations: Sequence[EvaluatedSetup],
    output_dir: Path, render: bool = True,
) -> ReportBundle:
    by_symbol = {item.symbol: item for item in evaluations}
    original_order = {symbol: index for index, symbol in enumerate(symbols)}
    ordered = [by_symbol.get(symbol) or EvaluatedSetup.unavailable(symbol, ("EVALUATION_MISSING",)) for symbol in symbols]
    def ranking_key(item: EvaluatedSetup) -> tuple[Decimal, int]:
        score = item.candidate.rank_score if item.candidate else Decimal(max(item.direction_score or 0, item.range_score or 0))
        if item.decision is Decision.DATA_UNAVAILABLE:
            score = Decimal("-1")
        return (-score, original_order[item.symbol])
    ordered.sort(key=ranking_key)
    rows = []
    qualified: list[SelectableCandidate] = []
    for rank, item in enumerate(ordered, 1):
        symbol = item.symbol
        candidate = item.candidate
        if item.decision is Decision.TRADE and candidate is not None:
            qualified.append(candidate)
        rows.append({
            "rank": rank, "symbol": symbol,
            "status": "PENDING" if item.decision is Decision.DATA_UNAVAILABLE else "EVALUATED",
            "decision": item.decision.value,
            "structure": candidate.structure_type.value if candidate else None,
            "direction_score": item.direction_score, "range_score": item.range_score,
            "premium_score": item.premium_score,
            "expected_value": str(item.expected_value) if item.expected_value is not None else None,
            "reason": ", ".join(item.reason_codes) if item.reason_codes else "Qualified by current evidence.",
            "reason_codes": list(item.reason_codes), "evidence_id": item.evidence_id,
        })
    selection = PortfolioSelector().select(qualified, (), Decimal("0"), 0)
    selected = [{
        "symbol": candidate.symbol, "candidate_id": candidate.candidate_id,
        "structure": candidate.structure_type.value, "maximum_loss": str(candidate.maximum_loss),
        "rank_score": str(candidate.rank_score),
    } for candidate in selection.selected]
    unavailable = sum(row["decision"] == Decision.DATA_UNAVAILABLE.value for row in rows)
    summary = {
        "paper_only": True, "module_id": "OPTION-001", "strategy_type": "0DTE_OPTIONS",
        "order_submission_enabled": False,
        "trade_date": trade_date, "market_session": "CURRENT",
        "best_neutral": next((row["symbol"] for row in rows if row["structure"] in {"IRON_CONDOR", "IRON_BUTTERFLY"}), None),
        "best_directional": next((row["symbol"] for row in rows if row["structure"] in {"PUT_CREDIT_SPREAD", "CALL_CREDIT_SPREAD"}), None),
        "selected_count": len(selected), "open_count": 0, "completed_count": 0,
        "health": "PENDING" if unavailable == len(rows) else ("DEGRADED" if unavailable else "HEALTHY"),
        "rejected_candidates": [row for row in rows if row["decision"] == Decision.NO_TRADE.value],
    }
    positions = {"paper_only": True, "order_submission_enabled": False, "trade_date": trade_date, "selected": selected, "open": [], "completed": []}
    experience = {"paper_only": True, "order_submission_enabled": False, "trade_date": trade_date, "mode": "SHADOW_ONLY", "ranking_influence": False, "symbols": []}
    bundle = ReportBundle(summary, rows, positions, experience)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write(output_dir / "option_001_summary.json", summary)
    _write(output_dir / "option_001_leaderboard.json", {"paper_only": True, "order_submission_enabled": False, "trade_date": trade_date, "leaderboard": rows})
    _write(output_dir / "option_001_positions.json", positions)
    _write(output_dir / "option_001_experience.json", experience)
    if render:
        from option_bot.dashboard import DashboardRenderer
        (output_dir / "option_001_dashboard.html").write_text(DashboardRenderer().render(bundle), encoding="utf-8")
    return bundle
