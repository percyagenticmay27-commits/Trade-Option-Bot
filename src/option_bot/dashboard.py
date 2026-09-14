"""Standalone, escaped rendering from the immutable JSON report contract."""

from __future__ import annotations

import html
from pathlib import Path

from option_bot.reporting import ReportBundle


ROOT = Path(__file__).parents[2]


def _value(value) -> str:
    return "Not available" if value is None else html.escape(str(value))


class DashboardRenderer:
    def render(self, bundle: ReportBundle) -> str:
        summary = bundle.summary
        rows = "".join(
            "<tr data-symbol-row='" + html.escape(row["symbol"], quote=True) + "'>"
            f"<td class='num'>{row['rank']}</td><td><strong>{html.escape(row['symbol'])}</strong></td>"
            f"<td><span class='badge pending'>{html.escape(row['status'])}</span></td>"
            f"<td>{_value(row['decision'])}</td><td>{_value(row['structure'])}</td>"
            f"<td class='num'>{_value(row['direction_score'])}</td><td class='num'>{_value(row['range_score'])}</td>"
            f"<td class='num'>{_value(row['premium_score'])}</td><td class='num'>{_value(row['expected_value'])}</td>"
            f"<td>{html.escape(row['reason'])}<details data-evidence-id='{html.escape(row['evidence_id'], quote=True)}'><summary>Evidence details</summary><div class='detail-body'>Current verified evidence is not available.</div></details></td></tr>"
            for row in bundle.leaderboard
        )
        content = f"""
<div class="paper-banner" role="status">PAPER TRADING ONLY — no live orders or capital movement</div>
<header class="hero"><div><h1>OPTION-001</h1><p>Evidence-driven 0DTE options</p></div><div class="session"><strong>Market session</strong><br>{_value(summary['market_session'])}<br>{html.escape(summary['trade_date'])} ET</div></header>
<section class="grid primary" aria-label="Primary opportunities"><article class="card decision"><h2>Best neutral setup</h2><div class="metric">{_value(summary['best_neutral'])}</div><p class="muted">Condor or butterfly only when range evidence qualifies.</p></article><article class="card decision"><h2>Best directional setup</h2><div class="metric">{_value(summary['best_directional'])}</div><p class="muted">Credit spread only when direction evidence qualifies.</p></article></section>
<section class="grid lifecycle"><article class="card"><h2>Selected trades</h2><div class="metric">{summary['selected_count']}</div></article><article class="card"><h2>Open positions</h2><div class="metric">{summary['open_count']}</div></article><article class="card"><h2>Completed trades</h2><div class="metric">{summary['completed_count']}</div></article></section>
<section class="panel table-panel"><div class="table-heading"><div><h2>Daily 0DTE leaderboard</h2><span class="muted">All governed symbols; unavailable values remain unavailable.</span></div><input aria-label="Filter symbols" data-symbol-filter type="search" placeholder="Filter symbols"></div><div class="table-wrap"><table><thead><tr><th scope="col">Rank</th><th scope="col">Symbol</th><th scope="col">Status</th><th scope="col">Decision</th><th scope="col">Structure</th><th scope="col">Direction</th><th scope="col">Range</th><th scope="col">Premium</th><th scope="col">Expected value</th><th scope="col">Evidence</th></tr></thead><tbody>{rows}</tbody></table></div></section>
<section class="grid lower"><article class="panel"><h2>Rejected candidates</h2><div class="empty">No verified rejection records are available.</div></article><article class="panel"><h2>Experience Learner</h2><span class="badge watch">SHADOW ONLY</span><p class="muted">Predictions are observed but do not influence active rankings.</p></article></section>
<section class="panel" style="margin-top:18px"><h2>System health</h2><span class="badge pending">{html.escape(summary['health'])}</span><p class="muted">Provider and event evidence must be current before entry.</p></section>
"""
        template = (ROOT / "templates/dashboard.html.j2").read_text(encoding="utf-8")
        style = (ROOT / "static/option-bot.css").read_text(encoding="utf-8")
        script = (ROOT / "static/option-bot.js").read_text(encoding="utf-8")
        return template.replace("{{STYLE}}", style).replace("{{CONTENT}}", content).replace("{{SCRIPT}}", script)
