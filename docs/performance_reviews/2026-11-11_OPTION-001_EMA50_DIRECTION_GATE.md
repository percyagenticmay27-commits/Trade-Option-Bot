# OPTION-001 paper-only direction gate: VWAP + 5-minute EMA50

**Approved by user November 11, 2026.** Status: deployed on the DigitalOcean `Trade-Option-Bot` working tree and verified by unit/integration tests; first fully scheduled live-paper cycle with the new multi-session data collection remains to be observed. **No live broker orders.**

## Changed direction behavior

- **Bullish put credit** (and existing bullish debit where supported): current SPY 5-minute reference price must be **above both session VWAP and the 50-period EMA**, and EMA50 must be **rising**.
- **Bearish call credit** (and existing bearish debit where supported): price must be **below both session VWAP and the 50-period EMA**, and EMA50 must be **falling**.
- EMA50 trend direction is the current EMA50 **minus its value three completed five-minute bars earlier** (15-minute slope).
- Neutral-range/condor policies continue to rely on existing regime and range checks; no new EMA50 veto is applied to them.
- Any directional conflict, flat EMA50, or insufficient history means **NO NEW DIRECTIONAL PAPER ENTRY** and an explicit `VWAP_EMA50_TREND_CONFLICT` or `EMA50_WARMUP_UNAVAILABLE_REQUIRE_53_COMPLETED_5MIN_BARS` diagnostic. Never invert an unconfirmed direction or invent missing history.
- This is a mandatory *direction* filter, independent of the technical score. Existing score policy `ADVISORY_DIRECTION_AND_RANKING` is unchanged, as are all risk, POP, credit-return, entry-time, management and exit rules.

## Data requirements

At least 53 original-source, regular-session *completed* 5-minute bars are required. Fetch previous trading session **plus** today from the authorized Robinhood read-only tool and supply the same merged, timestamp-preserving bars to the pre-lookup planner and final research snapshot. One session alone yielded only 23 bars at 10:26 a.m. CT on Nov. 11 and must not be used as an EMA50 approximation. Four existing Option Bot automation prompts were updated to request both sessions and preserve their schedules.

## Verification

- Red-green tests for bullish/bearish EMA50 agreement, opposing/flat trend, price on wrong side, missing history, and preserved neutral regime.
- Entire installed project test suite: **346 passed** (four third-party deprecation warnings).
- Authorized Robinhood research tool returned **120 real 5-minute SPY bars** for Nov. 10–11, 2026, verifying two-session coverage exists.
- A dry-run of the directional collector using those actual bars calculated **EMA50 757.331**, **three-bar EMA slope +0.498**, **SPY reference price 761.17**, **VWAP 758.360**, resulting in `BULLISH` planning. This was a data calculation only, **not a paper purchase**.
- First future production-scheduled paper scan must still be verified to ensure the automation really publishes at least 53 completed bars for all required symbols. If not, new directional entry correctly remains blocked.

## Scope protection

Only `src/option_bot/indicators.py`, `src/option_bot/collection_policy.py`, `src/option_bot/live_scan.py` and the corresponding new/updated tests were modified for this rule. No existing completed trades, paper positions, paper P/L, strategy risk parameters, or production schedules were altered. The existing working tree contains unrelated pre-existing source edits; do not sweep them into this limited changeset. This review record is for preserving the user-authorized change and verifying behavior on subsequent paper sessions.
