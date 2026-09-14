"""Portfolio-level selection across ranked 0DTE candidates."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Sequence

from option_bot.domain import StructureType


NEUTRAL_STRUCTURES = {StructureType.IRON_CONDOR, StructureType.IRON_BUTTERFLY}


@dataclass(frozen=True)
class SelectableCandidate:
    symbol: str
    candidate_id: str
    structure_type: StructureType
    rank_score: Decimal
    maximum_loss: Decimal
    exposure_group: str
    correlation_justified: bool = False


@dataclass(frozen=True)
class SelectionResult:
    selected: tuple[SelectableCandidate, ...]
    rejected: Mapping[str, str]
    reason_codes: tuple[str, ...] = ()


class PortfolioSelector:
    def __init__(self, max_entries: int = 2, daily_loss_limit: Decimal = Decimal("200")):
        self.max_entries = max_entries
        self.daily_loss_limit = daily_loss_limit

    def select(self, ranked: Sequence[SelectableCandidate], open_positions: Sequence[str], daily_defined_loss: Decimal, entry_count: int) -> SelectionResult:
        remaining_slots = self.max_entries - entry_count
        if remaining_slots <= 0 or daily_defined_loss >= self.daily_loss_limit:
            return SelectionResult((), {}, ("DAILY_LIMIT_EXHAUSTED",))
        available = [item for item in ranked if item.symbol not in set(open_positions)]
        available.sort(key=lambda item: item.rank_score, reverse=True)
        neutral = [item for item in available if item.structure_type in NEUTRAL_STRUCTURES]
        ordered = ([neutral[0]] if neutral else []) + [item for item in available if not neutral or item.candidate_id != neutral[0].candidate_id]
        selected: list[SelectableCandidate] = []
        rejected: dict[str, str] = {}
        committed_loss = daily_defined_loss
        for item in ordered:
            if len(selected) >= remaining_slots:
                break
            same_group = any(chosen.exposure_group == item.exposure_group for chosen in selected)
            if same_group and not item.correlation_justified:
                rejected[item.symbol] = "CORRELATED_EXPOSURE"
                continue
            if committed_loss + item.maximum_loss > self.daily_loss_limit:
                rejected[item.symbol] = "DAILY_LOSS_LIMIT"
                continue
            selected.append(item)
            committed_loss += item.maximum_loss
        reasons = ("NO_QUALIFYING_TRADE",) if not selected and not ranked else ()
        return SelectionResult(tuple(selected), rejected, reasons)
