"""Shadow-only symbol learner boundary with no runtime promotion path."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from option_bot.storage import AuditRepository


@dataclass(frozen=True)
class ShadowPrediction:
    symbol: str
    probability: Decimal
    predicted_class: str
    model_version: str


@dataclass(frozen=True)
class ShadowObservationResult:
    active_rank_score: Decimal
    record_id: int


class ShadowLearner:
    def __init__(self, repository: AuditRepository, promote: bool = False):
        if promote:
            raise ValueError("shadow promotion requires offline validation and a code release")
        self.repository = repository
        self.promotion_enabled = False

    def observe(self, prediction: ShadowPrediction, cycle_id: str, active_rank_score: Decimal, source_time: datetime) -> ShadowObservationResult:
        record_id = self.repository.record_evidence(
            f"shadow:{cycle_id}:{prediction.symbol}",
            {"kind": "shadow_prediction", "symbol": prediction.symbol, "probability": str(prediction.probability), "predicted_class": prediction.predicted_class, "model_version": prediction.model_version, "ranking_influence": False},
            "shadow-isolated", prediction.model_version, source_time,
        )
        return ShadowObservationResult(active_rank_score, record_id)
