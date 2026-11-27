# EMA250/450 dedicated research feed

The EMA shadow reads `results/ema250_450_shadow_research.json` exclusively.
It no longer silently falls back to the baseline's zero-bar management file.
No baseline scanner, config, schedule or ledger code is changed by this repair.

## Publishing

Collect actual read-only provider evidence into a normalized source document,
then run from the project root:

```sh
.venv/bin/python -m option_bot.ema_shadow_research --source results/ema250_450_shadow_incoming_research.json --output-dir results
```

The source must use ROBINHOOD_MCP_RESEARCH, research_only=true and
order_submission_enabled=false. Both SPX and XSP must specify
bar_source_symbol=SPY and identical normalized five-minute SPY OHLCV bars,
with timezone-aware original timestamps, positive volume, valid OHLC and
at least 450 completed RTH bars. Do not interpolate missing bars. Collect a
consistent longer warmup when possible for EMA reproducibility.

Actual directional option contracts, fresh provider leg quotes and verified
market_context references remain necessary for entry. A history-only source
may be published for diagnostics; it explicitly reports missing option quotes
and does not bypass contract, event or position checks. Current publication
time never makes old bars or quotes current.

## Automatic cycle handoff

On each EMA variant cycle, refresh checks EMA250_450_RESEARCH_INPUT, the active
ROBINHOOD_RESEARCH_SNAPSHOT_PATH, the early-reversal provider document and the
default provider document for a valid newer source. Publication is atomic and
preserves the source envelope and individual provider timestamps. Stale,
short-history, malformed or management-only zero-bar input cannot overwrite
a valid dedicated feed. The other shadow variant retains its existing source
selection behavior.

Health is published to `results/ema250_450_shadow_research_health.json`.
Missing/stale bars or quotes create a shadow-specific durable request at
`results/ema250_450_shadow_refresh_request.json`. The existing four option
lookup jobs were instructed to collect/publish this feed independently, and
run only the EMA shadow on existing authorized entry checkpoints when the
baseline is waiting or blocked. Schedules and management-only checkpoints
are unchanged; no new polling job is installed.

## Verification, November 27, 2026

64 relevant tests passed, including active handoff, exact timestamp preservation,
wick/boundary rejection, invalid-source rejection, stale-source nonreplacement,
zero-bar management nonreplacement and baseline-file immutability.
A deployed management-only shadow run loaded 666 actual completed SPY bars
through the dedicated file for SPX/XSP, without changing baseline ledger,
summary or provider file hashes. Its historical trades were retained.
The history ended at 12:55 ET; it was marked stale at the later verification
time and no current option quotes were claimed. No new position was opened.
