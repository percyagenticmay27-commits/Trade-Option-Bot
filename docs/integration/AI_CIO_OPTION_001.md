# AI CIO integration — OPTION-001

The option module publishes `results/ai_cio_option_001.json` using schema `schemas/option-module-summary-v1.schema.json`.

The AI CIO host may read and display this file. It must not use the summary contract to:

- mutate the option module's audit ledger;
- trigger, cancel, or alter an order;
- change evidence, rankings, risk limits, or position state;
- bypass the paper-only Alpaca endpoint gate;
- promote Experience Learner shadow predictions.

The contract identifies module `OPTION-001`, strategy `0DTE_OPTIONS`, version `1.0`, and always publishes `paper_only: true`. It includes UTC and ET timestamps, session phase, counts, nullable P&L and opportunity fields, risk usage, data freshness, health/blockers, and a validated dashboard URL.

Unavailable values remain JSON `null` and must be displayed as Pending or Not available. They must never be converted to zero. When health is blocked or freshness is unavailable, at least one blocker is required.

The View link should resolve `dashboard_url` inside the AI CIO host. Root-relative paths and absolute HTTPS URLs are accepted; protocol-relative, JavaScript, HTTP, FTP, and other URL forms are rejected.
