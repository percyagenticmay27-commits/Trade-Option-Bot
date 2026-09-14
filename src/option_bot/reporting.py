"""Deterministic JSON-first report contracts for OPTION-001."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from option_bot.config import REQUIRED_SYMBOLS


@dataclass
class ReportBundle:
    summary: dict
    leaderboard: list[dict]
    positions: dict
    experience: dict


class ReportBuilder:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def build(self, trade_date: str, render: bool = True) -> ReportBundle:
        leaderboard = [{
            "rank": index, "symbol": symbol, "status": "PENDING",
            "decision": "DATA_UNAVAILABLE", "structure": None,
            "direction_score": None, "range_score": None, "premium_score": None,
            "expected_value": None, "reason": "Current session evidence is not available.",
            "evidence_id": f"{trade_date}:{symbol}",
        } for index, symbol in enumerate(REQUIRED_SYMBOLS, 1)]
        summary = {
            "paper_only": True, "module_id": "OPTION-001", "strategy_type": "0DTE_OPTIONS",
            "trade_date": trade_date, "market_session": "Not available",
            "best_neutral": None, "best_directional": None,
            "selected_count": 0, "open_count": 0, "completed_count": 0,
            "health": "PENDING", "rejected_candidates": [],
        }
        positions = {"paper_only": True, "trade_date": trade_date, "selected": [], "open": [], "completed": []}
        experience = {"paper_only": True, "trade_date": trade_date, "mode": "SHADOW_ONLY", "ranking_influence": False, "symbols": []}
        bundle = ReportBundle(summary, leaderboard, positions, experience)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._write("option_001_summary.json", summary)
        self._write("option_001_leaderboard.json", {"paper_only": True, "trade_date": trade_date, "leaderboard": leaderboard})
        self._write("option_001_positions.json", positions)
        self._write("option_001_experience.json", experience)
        if render:
            from option_bot.dashboard import DashboardRenderer
            (self.output_dir / "option_001_dashboard.html").write_text(DashboardRenderer().render(bundle), encoding="utf-8")
        return bundle

    def _write(self, name: str, payload: dict) -> None:
        (self.output_dir / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
