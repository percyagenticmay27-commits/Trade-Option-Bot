"""Versioned numeric evidence scoring with canonical audit output."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from option_bot.indicators import IndicatorSnapshot
from option_bot.providers.base import Availability, EventGateEvidence, OptionSurface


@dataclass(frozen=True)
class EvidenceBundle:
    available: bool
    direction_score: int
    range_score: int
    premium_score: int
    evidence_confidence: Decimal
    model_version: str
    model_hash: str
    reason_codes: tuple[str, ...]
    implied_probability: Decimal | None
    calibrated_probability: Decimal | None

    def canonical_json(self) -> str:
        def encode(value: Any) -> Any:
            if isinstance(value, Decimal):
                return str(value)
            if isinstance(value, tuple):
                return [encode(item) for item in value]
            if isinstance(value, dict):
                return {key: encode(item) for key, item in value.items()}
            return value
        return json.dumps(encode(asdict(self)), sort_keys=True, separators=(",", ":"))


class EvidenceEngine:
    def __init__(self, model: dict[str, Any], model_hash: str):
        self.model = model
        self.model_hash = model_hash

    @classmethod
    def from_file(cls, path: Path) -> "EvidenceEngine":
        raw = path.read_bytes()
        return cls(json.loads(raw), hashlib.sha256(raw).hexdigest())

    def score(self, snapshot: IndicatorSnapshot, option_surface: OptionSurface, events: EventGateEvidence) -> EvidenceBundle:
        reasons = []
        if not snapshot.available:
            reasons.append("INDICATORS_UNAVAILABLE")
        if option_surface.availability is not Availability.AVAILABLE:
            reasons.append("OPTION_SURFACE_UNAVAILABLE")
        if events.availability is not Availability.AVAILABLE:
            reasons.append("EVENT_GATE_UNAVAILABLE")
        if events.blocked:
            reasons.append("EVENT_RISK_BLOCKED")
        if reasons:
            return EvidenceBundle(False, 0, 0, 0, Decimal("0.00"), self.model["version"], self.model_hash, tuple(reasons), None, None)
        weights = self.model["weights"]
        score = 0
        score += weights["vwap"] if snapshot.price > snapshot.vwap else 0
        score += weights["ema"] if snapshot.ema9 > snapshot.ema20 else 0
        score += weights["structure"] if snapshot.bullish_structure else 0
        score += weights["adx"] if snapshot.adx14 >= 20 else 0
        score += weights["relative_volume"] if snapshot.relative_volume >= 1 else 0
        score += weights["market_alignment"] if snapshot.market_alignment >= 2 else 0
        range_score = 100 if snapshot.adx14 <= self.model["neutral_adx_max"] and snapshot.chop14 >= self.model["neutral_chop_min"] else 0
        return EvidenceBundle(True, score, range_score, 70, Decimal("1.00"), self.model["version"], self.model_hash, (), None, None)
