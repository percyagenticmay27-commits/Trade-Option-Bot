"""Read-only OPTION-001 summary contract consumed by the AI CIO host."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo


ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class OptionModuleSummaryV1:
    contract_version: str
    module_id: str
    strategy_type: str
    paper_only: bool
    timestamp_utc: str
    timestamp_et: str
    session_phase: str
    eligible_count: int
    open_position_count: int
    realized_pnl: str | None
    open_pnl: str | None
    risk_used: str
    risk_limit: str
    risk_remaining: str
    best_opportunity: str | None
    freshness: str
    health: str
    blockers: tuple[str, ...]
    dashboard_url: str

    def to_dict(self) -> dict:
        result = asdict(self)
        result["blockers"] = list(self.blockers)
        return result

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    def publish(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


class AiCioContractBuilder:
    @staticmethod
    def _dashboard_url(value: str) -> str:
        if value.startswith("/") and not value.startswith("//"):
            return value
        parsed = urlparse(value)
        if parsed.scheme == "https" and parsed.netloc:
            return value
        raise ValueError("dashboard URL must be root-relative or absolute HTTPS")

    def build(
        self, *, as_of: datetime, session_phase: str, eligible_count: int,
        open_position_count: int, realized_pnl: Decimal | None, open_pnl: Decimal | None,
        risk_used: Decimal, risk_limit: Decimal, best_opportunity: str | None,
        freshness: str, health: str, blockers: tuple[str, ...], dashboard_url: str,
    ) -> OptionModuleSummaryV1:
        if as_of.tzinfo is None:
            raise ValueError("contract timestamp must be timezone-aware")
        if eligible_count < 0 or open_position_count < 0:
            raise ValueError("counts cannot be negative")
        if risk_used < 0 or risk_limit < 0 or risk_used > risk_limit:
            raise ValueError("risk usage must be within the governed limit")
        if (health == "BLOCKED" or freshness == "UNAVAILABLE") and not blockers:
            raise ValueError("blocked or unavailable contract requires a blocker")
        observed_et = as_of.astimezone(ET)
        observed_utc = as_of.astimezone(timezone.utc)
        return OptionModuleSummaryV1(
            contract_version="1.0", module_id="OPTION-001", strategy_type="0DTE_OPTIONS",
            paper_only=True, timestamp_utc=observed_utc.isoformat(), timestamp_et=observed_et.isoformat(),
            session_phase=session_phase, eligible_count=eligible_count,
            open_position_count=open_position_count,
            realized_pnl=None if realized_pnl is None else str(realized_pnl),
            open_pnl=None if open_pnl is None else str(open_pnl),
            risk_used=str(risk_used), risk_limit=str(risk_limit),
            risk_remaining=str(risk_limit - risk_used), best_opportunity=best_opportunity,
            freshness=freshness, health=health, blockers=tuple(blockers),
            dashboard_url=self._dashboard_url(dashboard_url),
        )
