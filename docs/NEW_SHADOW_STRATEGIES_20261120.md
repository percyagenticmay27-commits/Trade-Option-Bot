# OPTION-001 additional shadow models (November 20, 2026)

Both are new **independent, paper-only, SPXW/XSP** research books, added alongside the existing OPTION-001 baseline, EMA9/20 early reversal and original immediate Opening Range/VWAP regime shadow. The original algorithms, positions, historical P/L and risk settings are not retroactively modified. Five books have distinct ledgers, observations and daily P/L.

## Opening Range Breakout + Retest (`OPENING_RANGE_BREAKOUT_RETEST_SHADOW_V1`)

- Uses **SPY's completed NY RTH five-minute bars** as the index signal proxy, then reuses the approved contemporaneous SPY→SPX/XSP contract projection for short strikes.
- Forms opening range from 09:30–09:45 ET; requires two consecutive completed five-minute closes beyond the high for bullish, or below the low for bearish, both on corresponding sides of session VWAP.
- Does **not** trade that first breakout. After confirmation, a different, subsequent completed bar must wick to within `min(opening_range_width / 4, ATR14 * 0.15)` of the broken boundary and close back outside the range in the original breakout direction. The latest completed bar must remain outside the range and on the proper side of VWAP. A retest cannot occur on the same candle as original two-close confirmation.
- A lost range boundary before the retest invalidates the setup. Entry pending when the technical retest or source evidence is missing; no forced entries, retrospective fills, or use of current partial candles.
- Bullish: consider defined-risk **put credit**. Bearish: consider defined-risk **call credit**. Never naked short. Uses same approved option structuring, event gate, minimum net credit return, risk sizing, recent full-leg quotes and paper manager as the existing Opening Range shadow. No condor in this model: it specifically tests directional breakout/retest behavior.

## EMA 250 / EMA 450, five minutes (`EMA250_EMA450_5M_SHADOW_V1`)

- Exactly **EMA250 above EMA450 = bullish**; **EMA450 above EMA250 = bearish**. Both EMAs are computed over the last 450+ **completed SPY NY regular-session five-minute bars**, continuously across sessions (not reset at each open). Fewer than 450 bars blocks entry.
- Updated November 25: `EMA_OR15_VWAP_V2_20261125`. EMA ordering provides bias, not permission to enter. Freeze the high/low of the 09:30, 09:35 and 09:40 ET bars. Only a subsequent **completed five-minute close strictly outside that range** confirms a break; wicks and equality do not count. The first qualifying close is sufficient; two closes or a retest are not required. Earliest possible confirmation is 09:50 ET (08:50 CT).
- **Price crossing session VWAP in the trade direction is mandatory.** Confirm it using consecutive completed closes relative to their contemporaneous VWAP values in the same session. VWAP may cross before or after the range break; the latest close must still be outside the range and on the appropriate VWAP side. A return inside the range cancels that excursion. LIN12 crossing alone is not a substitute for price crossing VWAP.
- HMA21 on the one-hour timeframe is optional and does not block entries in this version. No HMA confirmation is claimed by the signal engine. Equal EMAs, incomplete opening grids, stale bars and missing option evidence block entry.
- Version changes affect future evaluations only; retain previous trades and their P/L unchanged. Historical diagnostic below describes the old EMA-only rules, not the updated entry policy.
- Bullish favors defined-risk put credit; bearish favors defined-risk call credit. All verified risk, metadata, credit threshold, event and quote rules are inherited, including no live orders.

## Runner and management

- `src/option_bot/shadow_variant_signals.py`: pure, independently testable signals.
- `src/option_bot/shadow_variant_cycle.py`: run each model through the existing governed evaluation and local simulator with distinct ledgers and reports.
- `option_bot.cli` schedules both on every authorized `scan-once` and `manage-once`, including `SHADOW_EARLY_ENTRY_SCAN=1` when the existing directional wait handoff requires shadow-only entries. Management-only never erroneously evaluates stale entry bars, but continues to manage real held legs.
- `scripts/barney_post_session.py` independently reconciles expiry of all five books, including both new models.
- `results/option_001_three_strategy_comparison.json` retains its historic filename but now contains **five** separate strategy rows. The comparison sums **no pooled P/L**; different inception dates mean comparing cumulative profits alone is invalid.

## Direct historical diagnostic at original losing trade

At 2026-11-20 10:01:57 ET, using the archived **actual provider SPY bars**, original Opening Range reported bullish breakout with high 714.16; new breakout-retest shadow said `WAIT / BREAKOUT_RETEST_SUPPORT_OR_RESISTANCE_NOT_CONFIRMED`. At that same timestamp EMA250=729.4867 and EMA450=735.3803 on five-minute SPY, meaning the EMA trend model was **bearish** and proposed researching call credits only. The two models therefore would not replicate the original 7110/7105 bullish put entry at that moment. This is a signal diagnostic, **not** a backtested P/L claim or proof that a different entry would have won.

The new live paper books begin with **0 trades / $0 realized**, and will only accumulate records through future verified authorized scans. Never generate fictitious historic profits.
