"""Deterministic daily scan and portfolio-selection orchestration."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, time
from decimal import Decimal
from typing import Callable, Sequence
from zoneinfo import ZoneInfo

from option_bot.domain import Decision, StructureType
from option_bot.portfolio import PortfolioSelector, SelectableCandidate
from option_bot.storage import AuditRepository


ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class SymbolEvaluation:
    symbol: str
    decision: Decision
    candidate: SelectableCandidate | None
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class CycleResult:
    cycle_id: str
    as_of: datetime
    leaderboard: tuple[SymbolEvaluation, ...]
    selected: tuple[SelectableCandidate, ...]
    reason_codes: tuple[str, ...]
    manage_positions: bool = False

    def canonical_json(self) -> str:
        def default(value):
            if isinstance(value, (Decision, StructureType)):
                return value.value
            if isinstance(value, Decimal):
                return str(value)
            if isinstance(value, datetime):
                return value.isoformat()
            raise TypeError(type(value).__name__)
        return json.dumps(asdict(self), default=default, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_payload(cls, payload: dict) -> "CycleResult":
        def candidate(raw):
            if raw is None:
                return None
            return SelectableCandidate(
                raw["symbol"], raw["candidate_id"], StructureType(raw["structure_type"]),
                Decimal(raw["rank_score"]), Decimal(raw["maximum_loss"]),
                raw["exposure_group"], bool(raw["correlation_justified"]),
            )
        leaderboard = tuple(SymbolEvaluation(row["symbol"], Decision(row["decision"]), candidate(row["candidate"]), tuple(row["reason_codes"])) for row in payload["leaderboard"])
        return cls(payload["cycle_id"], datetime.fromisoformat(payload["as_of"]), leaderboard, tuple(candidate(row) for row in payload["selected"]), tuple(payload["reason_codes"]), bool(payload["manage_positions"]))


class DailyOrchestrator:
    def __init__(self, symbols: Sequence[str], evaluator: Callable[[str], SymbolEvaluation], selector: PortfolioSelector, repository: AuditRepository, market_is_open: Callable[[datetime], bool], order_submitter: Callable[[SelectableCandidate], None] | None = None):
        self.symbols = tuple(symbols)
        self.evaluator = evaluator
        self.selector = selector
        self.repository = repository
        self.market_is_open = market_is_open
        self.order_submitter = order_submitter

    def run_cycle(self, as_of: datetime, cycle_id: str) -> CycleResult:
        if as_of.tzinfo is None:
            raise ValueError("cycle time must be timezone-aware")
        observed = as_of.astimezone(ET)
        existing = self.repository.find("cycle", cycle_id)
        if existing is not None:
            return CycleResult.from_payload(existing["payload"])
        if not self.market_is_open(observed):
            return self._persist(CycleResult(cycle_id, observed, (), (), ("MARKET_CLOSED",)))
        current = observed.time().replace(tzinfo=None)
        if current >= time(15, 30):
            return self._persist(CycleResult(cycle_id, observed, (), (), ("MANDATORY_EXIT_WINDOW",), True))
        if current < time(9, 45):
            return self._persist(CycleResult(cycle_id, observed, (), (), ("BEFORE_ENTRY_WINDOW",)))
        if current > time(10, 30):
            return self._persist(CycleResult(cycle_id, observed, (), (), ("AFTER_ENTRY_WINDOW",), True))
        leaderboard = []
        for symbol in self.symbols:
            try:
                result = self.evaluator(symbol)
            except (ConnectionError, TimeoutError, ValueError):
                result = SymbolEvaluation(symbol, Decision.DATA_UNAVAILABLE, None, ("PROVIDER_UNAVAILABLE",))
            leaderboard.append(result)
        ranked = tuple(item.candidate for item in leaderboard if item.candidate is not None and item.decision is Decision.TRADE)
        selection = self.selector.select(ranked, (), Decimal("0"), 0)
        result = CycleResult(cycle_id, observed, tuple(leaderboard), selection.selected, selection.reason_codes)
        self._persist(result)
        if self.order_submitter is not None:
            for selected in selection.selected:
                self.order_submitter(selected)
        return result

    def _persist(self, result: CycleResult) -> CycleResult:
        self.repository.record_cycle(result.cycle_id, json.loads(result.canonical_json()), "runtime-config", "evidence-model-v1", result.as_of)
        return result
