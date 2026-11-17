# Third paper comparison: opening-range and VWAP regime confirmation

Authorized November 17, 2026. Forward paper research only. Keep OPTION-001 and the early-reversal shadow unchanged. No backdated fills, transferred positions, or additional real capital.

## V1 entry hypotheses (experimental, not optimized)

Use completed SPY regular-session five-minute bars as explicitly labeled SPX/XSP technical proxies. Underlying index spot and option strikes must still come from real SPX/XSP market evidence with the existing projection checks.

- Fix opening high/low from 8:30, 8:35, 8:40 a.m. CT bars at 8:45 CT.
- No entry on those three bars alone. Directional confirmation earliest 8:55 CT: two completed post-range closes beyond the same boundary and on the corresponding side of session VWAP, VWAP slope aligned, time-matched relative volume at least 1.0. ADX/CHOP cannot override that expansion back to neutral.
- Condor evaluation earliest 9:00 CT: six completed bars; inherited ADX <=20 and CHOP >=55; last three closes inside the opening range; both boundaries rejected after the opening period; at least two close-versus-contemporaneous-VWAP sign changes in the last six bars; absolute VWAP slope <=0.10 ATR per five-minute bar. Boundary rejection tolerance is min(quarter opening width, 0.15 ATR). Last candle body >1.5 ATR vetoes a neutral entry. No low-volume requirement or automatic veto solely because volume is high.
- Relative volume compares the most recent three completed slots with those exact slots in up to 20 earlier sessions, requiring at least three complete matching sessions. Missing history means DATA_UNAVAILABLE, not zero volume. These sample sizes and thresholds are hypotheses for forward evaluation.
- Bullish: put credit spread. Bearish: call credit spread. Confirmed range: iron condor. All other conditions WAIT. No directional debit or butterfly in V1.
- Condor shorts must clear both the defended opening range and inherited Bollinger boundaries after validated index projection. Every credit structure requires >=15% maximum profit/maximum loss, including condors. This fixes no other book's policy.

## Existing execution controls

Independent hypothetical ledger, inherited OPTION-001 risk limits ($500 daily defined risk, $500 SPX/$100 XSP per trade, two entries), existing entry end 11:00 CT and existing exit/Barney/low-delta holding policy. Original bid/ask, identity, event checks, settlement, modeled POP and <=60-second quote freshness remain mandatory. No new timer. Runs on existing scan/manage CLI ticks; management ticks permit entries only under the same explicit SHADOW_EARLY_ENTRY_SCAN=1 setting. close-all-paper does not authorize new entries.

The new signal controls entries. It does not introduce an untested regime-triggered forced exit. Record transitions; existing price/stop/time management stays authoritative for this initial comparison.

## Collection and ledger integration

`scripts/plan_option_collection.py` additionally writes `results/option_001_opening_range_shadow_plan.json`. Inspect its SPX/XSP directions and candidate sides separately from the main plan and early-reversal observation.

Publish fresh authentic research to `results/opening_range_shadow_research.json` in the existing Robinhood schema, or use fresh main research if the dedicated file does not exist. Never restamp a cached snapshot. A stale dedicated file fails closed. Collect both sides for a neutral signal and the signaled credit side for a directional signal even when another book waits. Refresh exact held-leg identities on all management cycles. Include several prior sessions of actual RTH bars for volume matching, benchmark context, and official settlement/spot metadata. Existing scripts prepare_robinhood_snapshot.py and the same provider schema can prepare a uniquely named raw input to the dedicated output; do not overwrite the main snapshot.

New outputs:

- `opening_range_shadow_paper_ledger.json`: fills and positions.
- `option_001_opening_range_shadow_latest.json`: current decision, evidence and performance.
- `option_001_opening_range_shadow_observations.jsonl`: append-only decisions including WAIT/data blockers.
- `option_001_three_strategy_comparison.json`: three independent books, verified wins/losses, realized P/L and closed-trade-sequence drawdown.
- `option_strategy_registry.json`: explicit registration of all three books and forward-only inception.

Never claim a verified win rate from unclosed trades. Older books have different inception dates: compare matched forward sessions, and report sample size. P/L follows the existing simulated ledger prices; no extra fee/slippage assumptions have been added.
