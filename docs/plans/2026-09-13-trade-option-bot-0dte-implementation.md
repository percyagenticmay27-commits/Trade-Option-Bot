# Trade-Option-Bot 0DTE Options Module Implementation Plan

> **For agentic workers:** Use the host's available task-by-task implementation workflow. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy a standalone, paper-only `OPTION-001 / 0DTE_OPTIONS` module that ranks 12 option underlyings, selects at most two evidence-backed defined-risk trades per day, manages them safely, learns from outcomes, and publishes a Swing/Dividend-style dashboard and AI CIO summary.

**Architecture:** A Python package separates provider adapters, immutable domain/payoff models, evidence scoring, optimal-delta structure generation, risk-governed paper execution, durable SQLite audit records, reporting, and orchestration. Alpaca supplies paper account and market/option data; code-enforced fail-closed controls prevent live endpoints and enforce all risk/time limits. The Experience Learner makes deterministic evidence decisions from Day 1, preserves all evaluated candidates, and keeps learned models in shadow mode until separately promoted.

**Tech Stack:** Python 3.10+, pytest, dataclasses/Pydantic-style validation, pandas, NumPy, SQLite, SQL migration files, Alpaca REST/WebSocket APIs, Jinja2 HTML templates, vanilla CSS/JavaScript, JSON/CSV/Markdown reports, systemd on Ubuntu.

## Global Constraints

- Repository name: private GitHub repository `percyagenticmay27-commits/Trade-Option-Bot`.
- Deployment target: `/home/tradebot/Trade-Option-Bot` on `ai-cio-platform`.
- GitHub is created first; server deployment occurs only after repository verification.
- Version 1 is paper-only. It contains no Robinhood order integration, no live Alpaca order path, and no capital movement.
- Startup must reject any Alpaca trading base URL other than `https://paper-api.alpaca.markets`.
- Module identity is `OPTION-001`; strategy type is `0DTE_OPTIONS`.
- Universe: `NVDA`, `GOOGL`, `AAPL`, `MSFT`, `AMZN`, `META`, `AVGO`, `TSLA`, `XSP`, `MRUT`, `MBTX`, and `DJX`.
- Excluded screenshot results: `GLDM`, `SSRM`, `ETH`, `XME`, `GDX`, and `MNMD`.
- Maximum defined loss is $100 per trade; combined daily defined loss is $200; maximum new positions is two per trading day.
- Entry window is 09:45–10:30 ET; all positions receive a mandatory close action by 15:30 ET.
- Intended active loss exit is 50% of the position's maximum possible loss or earlier thesis/underlying invalidation.
- Default profit management is 50% of original credit, recorded as a versioned rule for later validation.
- Iron condors and iron butterflies receive priority when range evidence qualifies; directional verticals require strong directional evidence.
- No missing or stale market, option, Greek, event, product, or settlement field may silently pass a gate.
- Delta is an input, not a guaranteed probability. Evidence confidence, market-implied estimates, and calibrated probabilities remain distinct.
- The Experience Learner decides from Day 1 using deterministic evidence; learned models are shadow-only until a separate governed promotion.
- Version 1 never intentionally holds an option position through expiration and never legs into a multi-leg structure.
- Wheel functionality is excluded from implementation; only an inert `WHEEL_OPTIONS` reserved identifier may appear in documentation/enum tests.
- AI-generated text may explain stored facts but cannot generate market facts or override scores, gates, selection, sizing, or exits.
- Existing Swing and Dividend repositories must not be modified during core module construction.

---

### Task 1: Create the private repository and paper-only package foundation

**Files (all proposed):**
- Create: `README.md`
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `src/option_bot/__init__.py`
- Create: `src/option_bot/config.py`
- Create: `src/option_bot/domain.py`
- Create: `configs/option-001.json`
- Create: `tests/test_config.py`
- Create: `tests/test_domain.py`
- Create: `docs/specs/2026-09-13-trade-option-bot-0dte-design.md`
- Create: `docs/plans/2026-09-13-trade-option-bot-0dte-implementation.md`

**Interfaces:**
- Consumes: environment variables `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`, `APCA_API_BASE_URL`, `OPTION_BOT_TIMEZONE`, and `OPTION_BOT_DB_PATH`.
- Produces: `OptionBotConfig.load(environment: Mapping[str, str], config_path: Path) -> OptionBotConfig`; enums `OperatingMode`, `StrategyType`, `Decision`, `StructureType`, and `LifecycleStatus`; immutable value types `Money`, `OptionLeg`, `OptionQuote`, `ProductMetadata`, `EvidenceTimestamp`, `TradeCandidate`, `PortfolioRiskState`, `GateDecision`, `PaperMultiLegOrder`, `PaperOrderResult`, `Position`, and `PositionAction`.

- [ ] **Step 1: Create the GitHub repository and clone it locally**

Create private repository `percyagenticmay27-commits/Trade-Option-Bot` with default branch `main`, clone it into a new isolated implementation workspace, and verify `git remote -v` points only to that repository. Do not add a remote for either existing bot.

- [ ] **Step 2: Add focused failing foundation tests**

`tests/test_config.py` must assert that configuration accepts exactly `https://paper-api.alpaca.markets`, rejects absent credentials, rejects every non-paper or malformed order base URL, fixes timezone to `America/New_York`, contains exactly the 12 governed symbols, enforces $100/$200/two-position limits, and reserves but disables `WHEEL_OPTIONS`.

`tests/test_domain.py` must assert immutable domain objects, positive option multipliers/strike widths, same-expiration legs, valid call/put sides, timezone-aware timestamps, explicit product settlement/exercise metadata, and construction invariants for candidate, order, position, risk-state, gate, and position-action types used by later tasks.

- [ ] **Step 3: Verify the relevant failure**

Run: `pytest tests/test_config.py tests/test_domain.py -q`

Expected: collection/import failure for missing `option_bot.config` and `option_bot.domain`.

- [ ] **Step 4: Implement the minimum foundation**

Add Python packaging compatible with the existing bots' `src/` plus `tests/` convention. Implement fail-closed configuration, immutable domain types, the exact symbol/risk/schedule configuration, sanitized logging helpers that never print secrets, and an `.env.example` containing names only. README must state paper-only boundaries and reproduce setup/test commands.

- [ ] **Step 5: Verify the focused pass and safety scan**

Run: `pytest tests/test_config.py tests/test_domain.py -q`

Expected: all foundation tests pass.

Run: `rg -n 'APCA_API_SECRET_KEY\s*=\s*[^<]|api\.alpaca\.markets/v2/orders' . --glob '!docs/**' --glob '!.env.example'`

Expected: no committed secret values and no live-order URL.

- [ ] **Step 6: Commit the passing deliverable**

```bash
git add README.md pyproject.toml requirements.txt .gitignore .env.example configs src/option_bot tests/test_config.py tests/test_domain.py docs
git commit -m "chore: establish paper-only option bot foundation"
```

### Task 2: Implement exact payoff, product, and risk mathematics

**Files (proposed):**
- Create: `src/option_bot/payoff.py`
- Create: `src/option_bot/risk.py`
- Create: `tests/test_payoff.py`
- Create: `tests/test_risk.py`

**Interfaces:**
- Consumes: `OptionLeg`, `Money`, `ProductMetadata`, configured per-trade/daily limits.
- Produces: `PayoffProfile.evaluate(legs: Sequence[OptionLeg], net_credit: Decimal, multiplier: int) -> PayoffProfile`; `PayoffProfile.pnl_at(price: Decimal) -> Money`; `RiskGovernor.validate_candidate(candidate: TradeCandidate, portfolio: PortfolioRiskState, now: datetime) -> GateDecision`.

- [ ] **Step 1: Add focused failing payoff tests**

Cover bull put spreads, bear call spreads, symmetric and asymmetric iron condors, iron butterflies, arbitrary four-leg expiration payoffs, net credit, maximum profit, maximum loss, upper/lower breakevens, $100 boundary acceptance, $100.01 rejection, $200 daily aggregate rejection, third-entry rejection, and one-contract structures that cannot be resized below $100.

- [ ] **Step 2: Verify the relevant failure**

Run: `pytest tests/test_payoff.py tests/test_risk.py -q`

Expected: imports fail because payoff and risk engines do not exist.

- [ ] **Step 3: Implement exact decimal-based calculations**

Use `Decimal`, not binary float, for strikes, premiums, and P&L. Derive worst-case payoff from all relevant strike intervals so unequal widths are correct. Implement code-enforced paper mode, limits, entry-count, entry-window, mandatory-exit, same-expiration, product metadata, and complete multi-leg requirements. Gate results contain stable reason codes and evidence.

- [ ] **Step 4: Verify focused and property-style boundary passes**

Run: `pytest tests/test_payoff.py tests/test_risk.py -q`

Expected: all payoff values and boundary decisions pass exactly.

- [ ] **Step 5: Run the affected suite and commit**

Run: `pytest -q`

Expected: all repository tests pass.

```bash
git add src/option_bot/payoff.py src/option_bot/risk.py tests/test_payoff.py tests/test_risk.py
git commit -m "feat: add exact option payoff and risk governance"
```

### Task 3: Add Alpaca market-data and paper-account adapters with replay fixtures

**Files (proposed):**
- Create: `src/option_bot/providers/base.py`
- Create: `src/option_bot/providers/alpaca_market.py`
- Create: `src/option_bot/providers/alpaca_paper.py`
- Create: `src/option_bot/providers/events.py`
- Create: `src/option_bot/providers/normalization.py`
- Create: `tests/fixtures/alpaca/aapl_chain.json`
- Create: `tests/fixtures/alpaca/xsp_contracts.json`
- Create: `tests/fixtures/alpaca/stale_chain.json`
- Create: `tests/fixtures/alpaca/missing_greeks.json`
- Create: `tests/test_alpaca_market.py`
- Create: `tests/test_alpaca_paper.py`
- Create: `tests/test_event_gate.py`

**Interfaces:**
- Produces: protocol `MarketDataProvider.get_session_snapshot(symbols, as_of) -> SessionSnapshot`; `MarketDataProvider.get_option_surface(symbol, expiration, as_of) -> OptionSurface`; `PaperBroker.submit_multileg(order: PaperMultiLegOrder) -> PaperOrderResult`; `PaperBroker.cancel(order_id: str) -> PaperOrderResult`; `EventProvider.get_event_gate(symbol, window) -> EventGateEvidence`.
- Safety: `AlpacaPaperClient` constructor accepts only the exact paper base URL; provider responses carry source timestamps, receive timestamps, entitlement/feed identifiers, and freshness status.

- [ ] **Step 1: Capture sanitized provider fixtures and failing contract tests**

Use read-only calls to capture representative AAPL and index-product payload shapes with credentials, account identifiers, request IDs, and unnecessary personal fields removed. Tests must cover active chain normalization, product metadata, quote/Greek parsing, unavailable XSP/MRUT/MBTX/DJX coverage, stale timestamps, crossed markets, missing Greeks, rate limits, timeouts, empty expirations, and event-source unavailability.

- [ ] **Step 2: Verify the relevant failure**

Run: `pytest tests/test_alpaca_market.py tests/test_alpaca_paper.py tests/test_event_gate.py -q`

Expected: provider protocols and adapters are missing.

- [ ] **Step 3: Implement adapters and fail-closed normalization**

Implement retry only for idempotent reads and status checks, bounded exponential backoff, explicit rate-limit evidence, and no retry that can duplicate an order. Normalize all timestamps to timezone-aware ET plus retained source timezone. Missing required option fields produce typed unavailable evidence. The event adapter aggregates configured authoritative calendars; if no configured event source succeeds, its gate is unavailable and blocks entry.

- [ ] **Step 4: Verify adapter behavior without network dependence**

Run: `pytest tests/test_alpaca_market.py tests/test_alpaca_paper.py tests/test_event_gate.py -q`

Expected: fixture-driven tests pass; no test sends an order or requires live credentials.

- [ ] **Step 5: Run suite and commit**

Run: `pytest -q`

Expected: all tests pass.

```bash
git add src/option_bot/providers tests/fixtures/alpaca tests/test_alpaca_market.py tests/test_alpaca_paper.py tests/test_event_gate.py
git commit -m "feat: add fail-closed Alpaca paper adapters"
```

### Task 4: Build indicators, evidence scores, and Day-1 Experience Learner

**Files (proposed):**
- Create: `src/option_bot/indicators.py`
- Create: `src/option_bot/evidence.py`
- Create: `src/option_bot/experience.py`
- Create: `configs/evidence-model-v1.json`
- Create: `tests/fixtures/bars/aapl_intraday.csv`
- Create: `tests/test_indicators.py`
- Create: `tests/test_evidence.py`
- Create: `tests/test_experience.py`

**Interfaces:**
- Produces: `IndicatorEngine.compute(bars_5m, bars_15m, market_context) -> IndicatorSnapshot`; `EvidenceEngine.score(snapshot, option_surface, events, model_version) -> EvidenceBundle`; `ExperienceLearner.decide(evidence: EvidenceBundle, history: ExperienceProfile) -> LearnerDecision`; `ExperienceLearner.observe(observation: OutcomeObservation) -> ExperienceUpdate`.

- [ ] **Step 1: Add exact indicator and evidence tests**

Assert session-reset VWAP, EMA(9/20), Wilder ADX(14), CHOP(14), ATR(14), relative volume, 09:30–09:45 opening range, previous-day levels, SPY/QQQ/sector alignment, bullish/bearish/neutral fixtures, unavailable-input propagation, score component totals, model/config hash retention, and separation of evidence confidence from implied/calibrated probabilities.

- [ ] **Step 2: Verify the relevant failure**

Run: `pytest tests/test_indicators.py tests/test_evidence.py tests/test_experience.py -q`

Expected: indicator/evidence/experience modules are missing.

- [ ] **Step 3: Implement deterministic versioned evidence decisions**

Implement pure indicator functions, explicit component weights, hard evidence completeness, stable direction/range/premium score schemas, and Day-1 `TRADE`, `WATCH`, `NO_TRADE`, or `DATA_UNAVAILABLE` decisions. The Experience Learner consumes only stored numeric evidence and prior versioned summaries; prose is generated from stored reason codes after the decision.

- [ ] **Step 4: Verify focused pass and reproducibility**

Run: `pytest tests/test_indicators.py tests/test_evidence.py tests/test_experience.py -q`

Expected: all expected numeric values and decisions pass; repeated input yields byte-equivalent canonical evidence JSON.

- [ ] **Step 5: Run suite and commit**

Run: `pytest -q`

Expected: all tests pass.

```bash
git add src/option_bot/indicators.py src/option_bot/evidence.py src/option_bot/experience.py configs/evidence-model-v1.json tests/fixtures/bars tests/test_indicators.py tests/test_evidence.py tests/test_experience.py
git commit -m "feat: add evidence-driven experience learner"
```

### Task 5: Generate structures and choose optimal deltas

**Files (proposed):**
- Create: `src/option_bot/probability.py`
- Create: `src/option_bot/structures.py`
- Create: `src/option_bot/delta_optimizer.py`
- Create: `tests/test_probability.py`
- Create: `tests/test_structures.py`
- Create: `tests/test_delta_optimizer.py`

**Interfaces:**
- Produces: `ProbabilityModel.estimate(context: ProbabilityContext) -> OutcomeDistribution`; `StructureGenerator.generate(surface: OptionSurface, evidence: EvidenceBundle, config: StructureConfig) -> Sequence[TradeCandidate]`; `DeltaOptimizer.rank(candidates, distributions, experience) -> Sequence[RankedCandidate]`.

- [ ] **Step 1: Add failing structure and delta-ladder tests**

Cover 0.08/0.10/0.12/0.15/0.18/0.20 short-delta search, conditional candidates through 0.25, unavailable exact-delta nearest-contract handling, asymmetric condors, bullish and bearish verticals, iron-butterfly body selection, support/resistance and expected-move clearance, $100 wing rejection, gamma/liquidity rejection, and preservation of every rejected delta with reason codes.

Probability tests must assert mutually exclusive outcome probabilities sum to one within decimal tolerance; separately report finish, touch, stop, target, range, and time-exit values; reject unversioned assumptions; and prohibit a mechanical `touch_probability = 2 * abs(delta)` rule.

- [ ] **Step 2: Verify the relevant failure**

Run: `pytest tests/test_probability.py tests/test_structures.py tests/test_delta_optimizer.py -q`

Expected: probability, structure, and optimizer modules are missing.

- [ ] **Step 3: Implement enumeration and expected-value ranking**

Generate only complete same-expiration structures. Use option delta as a market input, technical/expected-move boundaries as gates, and probability distributions for expected value. Implement `expected_net_value(outcomes, slippage, fees)` as `sum(outcome.probability * outcome.net_pnl for outcome in outcomes) - slippage - fees`; its tests must assert the exact formula and probability-total invariant. Rank by expected value, credit/max-loss efficiency, boundary clearance, liquidity, gamma safety, stop probability, and matching experience evidence. Butterfly bodies use expected landing zone, VWAP/opening equilibrium, high-volume price, technical convergence, and validated pinning evidence rather than the vertical delta ladder.

- [ ] **Step 4: Verify focused pass and remove ambiguous wording**

Run: `pytest tests/test_probability.py tests/test_structures.py tests/test_delta_optimizer.py -q`

Expected: all enumeration, rejection, probability, and ordering assertions pass.

Run: `rg -n '2\s*\*\s*(abs\()?delta|delta\s*\*\s*2' src/option_bot`

Expected: no simplistic doubled-delta touch rule.

- [ ] **Step 5: Run suite and commit**

Run: `pytest -q`

Expected: all tests pass.

```bash
git add src/option_bot/probability.py src/option_bot/structures.py src/option_bot/delta_optimizer.py tests/test_probability.py tests/test_structures.py tests/test_delta_optimizer.py
git commit -m "feat: optimize deltas across governed structures"
```

### Task 6: Add durable audit ledger, conservative fill model, and position lifecycle

**Files (proposed):**
- Create: `src/option_bot/storage.py`
- Create: `src/option_bot/fills.py`
- Create: `src/option_bot/positions.py`
- Create: `migrations/001_initial.sql`
- Create: `tests/test_storage.py`
- Create: `tests/test_fills.py`
- Create: `tests/test_positions.py`

**Interfaces:**
- Produces: `AuditRepository.record_cycle`, `record_evidence`, `record_candidate`, `record_order`, `record_fill`, `record_position_event`, `record_outcome`; `FillModel.evaluate(order, quote_sequence) -> FillDecision`; `PositionManager.evaluate(position, snapshot, now) -> PositionAction`.

- [ ] **Step 1: Add failing persistence and lifecycle tests**

Assert append-oriented records, superseding corrections, configuration/model hashes, source timestamps, complete delta-ladder persistence, idempotency across restarts, no midpoint assumption, limit improvement bounds, unfilled expiry at 10:30, incomplete multi-leg rejection, profit exit, thesis exit, boundary exit, 50%-of-max-loss exit, daily stop, stale-data safe state, and 15:30 mandatory exit.

- [ ] **Step 2: Verify the relevant failure**

Run: `pytest tests/test_storage.py tests/test_fills.py tests/test_positions.py -q`

Expected: storage/fill/position modules and schema are missing.

- [ ] **Step 3: Implement transactional lifecycle behavior**

Use SQLite transactions and unique idempotency keys. Preserve candidate and rejection evidence even when no order exists. A quote outage blocks entries; for an open position it creates an explicit degraded state and continues conservative underlying-based risk checks while retrying option valuation. Never mark missing data as zero P&L or a successful exit.

- [ ] **Step 4: Verify focused pass, restart, and migration behavior**

Run: `pytest tests/test_storage.py tests/test_fills.py tests/test_positions.py -q`

Expected: all persistence, replay, fill, and exit tests pass using temporary databases.

- [ ] **Step 5: Run suite and commit**

Run: `pytest -q`

Expected: all tests pass.

```bash
git add src/option_bot/storage.py src/option_bot/fills.py src/option_bot/positions.py migrations/001_initial.sql tests/test_storage.py tests/test_fills.py tests/test_positions.py
git commit -m "feat: add durable paper position lifecycle"
```

### Task 7: Orchestrate daily scanning, portfolio selection, and shadow learning

**Files (proposed):**
- Create: `src/option_bot/orchestrator.py`
- Create: `src/option_bot/portfolio.py`
- Create: `src/option_bot/shadow.py`
- Create: `src/option_bot/cli.py`
- Create: `tests/test_orchestrator.py`
- Create: `tests/test_portfolio.py`
- Create: `tests/test_shadow.py`

**Interfaces:**
- Produces: `DailyOrchestrator.run_cycle(as_of: datetime, cycle_id: str) -> CycleResult`; `PortfolioSelector.select(ranked, open_positions, daily_state) -> SelectionResult`; CLI commands `health`, `scan-once`, `manage-once`, `close-all-paper`, and `render-reports`.

- [ ] **Step 1: Add failing end-to-end orchestration tests**

Test zero/one/two selected trades, best neutral plus best directional choice, neutral-structure preference, correlated NVDA/AVGO exposure rejection or explicit governed justification, complete 12-symbol leaderboard, no qualifying trade, duplicate cycle, market closed, before 09:45, after 10:30, 15:30 close, daily limit exhaustion, provider outage, and a second-process restart.

Shadow tests assert outputs are stored but ignored by active ranking, promotion is impossible through runtime configuration, and active results remain identical when shadow predictions change.

- [ ] **Step 2: Verify the relevant failure**

Run: `pytest tests/test_orchestrator.py tests/test_portfolio.py tests/test_shadow.py -q`

Expected: orchestration, portfolio, and shadow modules are missing.

- [ ] **Step 3: Implement deterministic cycle orchestration**

Collect all 12 symbols, run gates/evidence/generation/ranking, apply portfolio limits, submit complete paper orders only in the entry window, manage open positions after the entry window, and persist a canonical `CycleResult`. Correlation checks use documented market/sector exposure evidence and return stable reason codes. CLI defaults to read-only health; state-changing paper commands require explicit subcommands and paper-only startup proof.

- [ ] **Step 4: Verify focused and full-flow passes**

Run: `pytest tests/test_orchestrator.py tests/test_portfolio.py tests/test_shadow.py -q`

Expected: all lifecycle scenarios pass without network or live credentials.

- [ ] **Step 5: Run suite and commit**

Run: `pytest -q`

Expected: all tests pass.

```bash
git add src/option_bot/orchestrator.py src/option_bot/portfolio.py src/option_bot/shadow.py src/option_bot/cli.py tests/test_orchestrator.py tests/test_portfolio.py tests/test_shadow.py
git commit -m "feat: orchestrate governed daily option selection"
```

### Task 8: Build reports and the standalone executive dashboard

**Files (proposed):**
- Create: `src/option_bot/reporting.py`
- Create: `src/option_bot/dashboard.py`
- Create: `templates/dashboard.html.j2`
- Create: `static/option-bot.css`
- Create: `static/option-bot.js`
- Create: `tests/test_reporting.py`
- Create: `tests/test_dashboard.py`
- Create: `results/.gitkeep`

**Interfaces:**
- Produces: `ReportBuilder.build(trade_date) -> ReportBundle`; `DashboardRenderer.render(report_bundle) -> str`; outputs `results/option_001_summary.json`, `results/option_001_leaderboard.json`, `results/option_001_positions.json`, `results/option_001_experience.json`, and `results/option_001_dashboard.html`.

- [ ] **Step 1: Inspect live visual conventions read-only and add failing render tests**

On `ai-cio-platform`, inspect the authoritative Swing and Dividend dashboard HTML/CSS/report contracts without editing either repository. Record reusable colors, typography, spacing, status badges, cards, table behavior, responsive breakpoints, accessibility contrast, and View-link conventions in `docs/references/dashboard-parity.md`. Do not copy business logic or secrets.

Tests assert the market/session header, complete 12-symbol table, best neutral/directional cards, selected/open/completed trades, Experience Learner section, rejected candidates, health panel, evidence drill-down links, paper-only banner, accessible table headers, mobile viewport metadata, and honest pending/unavailable values.

- [ ] **Step 2: Verify the relevant failure**

Run: `pytest tests/test_reporting.py tests/test_dashboard.py -q`

Expected: reporting/dashboard modules and templates are missing.

- [ ] **Step 3: Implement deterministic reports and matching UI**

Generate JSON first from ledger facts, then render HTML from the JSON contract. Keep the executive view compact and expose immutable evidence details through drill-down sections. Escape all text. CSS follows the recorded shared visual conventions while remaining standalone. JavaScript may filter/sort already-rendered data but cannot calculate trading decisions.

- [ ] **Step 4: Verify focused pass and rendered artifact**

Run: `pytest tests/test_reporting.py tests/test_dashboard.py -q`

Expected: report schemas and HTML assertions pass.

Run: `python -m option_bot.cli render-reports --fixture-date 2026-09-14`

Expected: all five report files are generated with `paper_only: true`; dashboard opens without external assets or console errors.

- [ ] **Step 5: Run suite and commit**

Run: `pytest -q`

Expected: all tests pass.

```bash
git add src/option_bot/reporting.py src/option_bot/dashboard.py templates static tests/test_reporting.py tests/test_dashboard.py results/.gitkeep docs/references/dashboard-parity.md
git commit -m "feat: add option module reports and dashboard"
```

### Task 9: Publish the AI CIO contract without coupling repositories

**Files (proposed):**
- Create: `src/option_bot/ai_cio_contract.py`
- Create: `schemas/option-module-summary-v1.schema.json`
- Create: `tests/test_ai_cio_contract.py`
- Create: `docs/integration/AI_CIO_OPTION_001.md`

**Interfaces:**
- Produces: `AiCioContractBuilder.build(cycle_result, report_bundle) -> OptionModuleSummaryV1`; output `results/ai_cio_option_001.json` with module ID, strategy type, paper status, session phase, eligible count, open-position count, realized/open P&L, risk used/remaining, best opportunity, freshness, health/blockers, and dashboard URL.

- [ ] **Step 1: Add failing schema and contract tests**

Assert exact `OPTION-001`, `0DTE_OPTIONS`, version `1.0`, `paper_only: true`, UTC/ET timestamps, nullable unavailable fields with blockers, no credentials or raw personal/account identifiers, relative/absolute dashboard URL validation, and deterministic JSON serialization.

- [ ] **Step 2: Verify the relevant failure**

Run: `pytest tests/test_ai_cio_contract.py -q`

Expected: contract module and schema are missing.

- [ ] **Step 3: Implement read-only publication**

Build the contract only from canonical cycle/report records. Document that AI CIO consumes the file but cannot mutate the ledger, trigger orders, or bypass governance. Do not modify the AI CIO, Swing, or Dividend repository in this task.

- [ ] **Step 4: Verify focused and schema passes**

Run: `pytest tests/test_ai_cio_contract.py -q`

Expected: contract instances validate against the JSON schema and security assertions pass.

- [ ] **Step 5: Run suite and commit**

Run: `pytest -q`

Expected: all tests pass.

```bash
git add src/option_bot/ai_cio_contract.py schemas/option-module-summary-v1.schema.json tests/test_ai_cio_contract.py docs/integration/AI_CIO_OPTION_001.md
git commit -m "feat: publish OPTION-001 AI CIO contract"
```

### Task 10: Package scheduling and deploy a supervised paper-only service

**Files (proposed):**
- Create: `scripts/run_option_bot.sh`
- Create: `deploy/systemd/trade-option-bot-scan.service`
- Create: `deploy/systemd/trade-option-bot-scan.timer`
- Create: `deploy/systemd/trade-option-bot-manage.service`
- Create: `deploy/systemd/trade-option-bot-manage.timer`
- Create: `deploy/systemd/trade-option-bot-close.service`
- Create: `deploy/systemd/trade-option-bot-close.timer`
- Create: `deploy/systemd/trade-option-bot-dashboard.service`
- Create: `tests/test_deployment_files.py`
- Create: `docs/DEPLOYMENT.md`
- Create: `docs/OPERATIONS.md`

**Interfaces:**
- Consumes: checked-out repository, `.venv`, root-owned/read-restricted environment file, paper Alpaca credentials, writable results/database paths.
- Produces: idempotent scheduled scan/manage/close invocations, dashboard service, health command, and rollback instructions.

- [ ] **Step 1: Add failing deployment-file tests**

Assert services run as `tradebot`, use explicit `/home/tradebot/Trade-Option-Bot` paths, never embed secrets, call only paper CLI commands, include overlap protection, observe ET/exchange-calendar logic in application code, run close enforcement before 15:30, restart the dashboard safely, and prohibit a live Alpaca base URL.

- [ ] **Step 2: Verify the relevant failure**

Run: `pytest tests/test_deployment_files.py -q`

Expected: deployment files are missing.

- [ ] **Step 3: Implement scripts, units, and operator documentation**

Document GitHub clone, virtual environment creation, dependency installation, environment-file permissions, migrations, dry run, service installation, health checks, logs, rollback, and credential rotation. Timers may invoke more frequently than signal generation, but application idempotency and schedule gates remain authoritative.

- [ ] **Step 4: Verify locally and push reviewed repository**

Run: `pytest -q`

Expected: complete suite passes.

Run: `python -m option_bot.cli health --config configs/option-001.json`

Expected: without deployment secrets, a clear `CONFIG_UNAVAILABLE` result and nonzero exit; with paper secrets in the supervised environment, `paper_only=true`, exact paper base URL, database writable, and provider status reported.

Run: `git status --short`

Expected: clean working tree before push.

- [ ] **Step 5: Commit and push the deployment deliverable**

```bash
git add scripts deploy tests/test_deployment_files.py docs/DEPLOYMENT.md docs/OPERATIONS.md
git commit -m "ops: package supervised paper-only deployment"
git push -u origin main
```

- [ ] **Step 6: Deploy to `ai-cio-platform` without root assumptions**

As `tradebot`, clone to `/home/tradebot/Trade-Option-Bot`, create `.venv`, install locked dependencies, configure the protected paper environment, migrate the database, run the full suite, and execute read-only health plus order-disabled dry run. If root/systemd access is required, stop and give the user exact reviewed `sudo` commands; do not attempt privilege escalation.

Expected before enabling paper order submission: health passes, all 12 symbols report supported or an explicit product/data blocker, no live endpoint exists, dashboard renders, AI CIO JSON validates, and dry run produces candidates/rejections without submitting an order.

- [ ] **Step 7: Enable paper simulation only after explicit approval**

After the user reviews dry-run evidence, enable Alpaca paper submission, run one supervised market-session cycle, verify the two-position/$100/$200/time gates, and confirm the ledger/dashboard/AI CIO outputs agree. Do not enable Robinhood or any live broker route.

## Unresolved externally observable decisions

1. **Economic/company event provider:** Alpaca corporate actions are defined, but the authoritative economic and company-event feed used by `EventProvider` must be selected before Task 3 can enable entries. Until selected and healthy, the event gate fails closed and the bot can only perform order-disabled research scans.
2. **AI CIO integration path and public dashboard URL:** The contract shape is fixed, but the authoritative live AI CIO repository/path, dashboard host/port, and View-link registration location must be confirmed during the read-only live-server parity inspection. No existing repository will be modified without a separate reviewed integration step.
3. **Alpaca entitlement and product coverage:** The implementation must verify the connected account's current stock-option feed and same-day contract support for each of XSP, MRUT, MBTX, and DJX. Unsupported products remain visible with `PRODUCT_UNAVAILABLE`; they are not silently replaced.
4. **Estimated fees:** The payoff engine will support a configured per-contract fee model and report zero only when explicitly configured. The exact paper comparison fee schedule must be chosen before performance is used for model promotion.
