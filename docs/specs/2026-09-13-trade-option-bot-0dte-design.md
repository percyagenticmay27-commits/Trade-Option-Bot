# Trade-Option-Bot 0DTE Options Module Design

**Date:** 2026-09-13  
**Repository:** `Trade-Option-Bot`  
**AI CIO registration:** `OPTION-001`  
**Initial strategy type:** `0DTE_OPTIONS`  
**Initial operating mode:** Paper only

## 1. Purpose

Trade-Option-Bot is a standalone AI CIO plugin-style module for evidence-backed 0DTE defined-risk option strategies. It scans a controlled symbol universe, ranks opportunities, selects no more than two paper trades per day, monitors them, closes them before expiration, and preserves all evidence and outcomes for continuous learning.

The bot must not force a trade. `WATCH`, `NO_TRADE`, and `DATA_UNAVAILABLE` are successful governed outcomes when evidence is incomplete or risk is unacceptable.

The repository is created on GitHub first and subsequently deployed to `ai-cio-platform`. It has a standalone dashboard matching the Swing and Dividend Bot look and feel and publishes a read-only registration contract and View link to the main AI CIO.

## 2. Scope

### Version 1

- Paper trading only through Alpaca's paper environment
- Alpaca market and options data
- Evidence-driven ranking of 12 configured underlyings
- Iron condors and iron butterflies preferred when range evidence qualifies
- Put or call credit spreads when directional evidence is strong
- Maximum two qualifying paper trades per day
- Standalone dashboard and AI CIO summary contract
- Durable evidence ledger and Experience Learner

### Later phase

`WHEEL_OPTIONS` will be a separate strategy engine within the same repository. It will cover cash-secured puts, assignment, share-lot state, and covered calls. Wheel behavior is explicitly excluded from Version 1 implementation because it is a multi-day lifecycle with stock obligations and different capital controls.

Robinhood may be evaluated as a separately approved live destination only after paper validation. Version 1 contains no Robinhood order integration and no live-order path.

## 3. Governed symbol universe

### Equity options

- `NVDA`
- `GOOGL`
- `AAPL`
- `MSFT`
- `AMZN`
- `META`
- `AVGO`
- `TSLA`

### Mini-index options

- `XSP` — S&P 500 Mini Index
- `MRUT` — Russell 2000 Mini Index
- `MBTX` — Bitcoin U.S. ETF Mini Index
- `DJX` — Dow Jones Industrial Average Mini Index

Every symbol is configuration-driven. A symbol is eligible on a given day only when the data provider confirms an active same-day expiration and supplies sufficient current data. Product metadata must identify settlement, exercise style, multiplier, last trading time, and expiration behavior. Equity and index products must not share assumed settlement rules.

The following screenshot search results are not in scope: `GLDM`, `SSRM`, `ETH`, `XME`, `GDX`, and `MNMD`.

## 4. Architecture

The system uses small, independently testable components:

1. **Market collector** — retrieves market clock, calendar, stock/index bars, option contracts, chains, quotes, Greeks, implied volatility, volume, open interest, corporate actions, and freshness metadata.
2. **Event gate** — evaluates economic releases, Federal Reserve events, earnings, company events, halts, and other binary risks.
3. **Indicator engine** — calculates 5-minute and 15-minute VWAP, EMA(9), EMA(20), ADX(14), CHOP(14), ATR(14), relative volume, opening range, previous-day levels, and market/sector alignment.
4. **Experience Learner** — makes Day-1 evidence-based decisions, records predictions and outcomes, maintains symbol/regime experience, and later runs learned models in shadow mode.
5. **Structure generator** — enumerates valid iron condors, iron butterflies, put credit spreads, and call credit spreads using available strikes.
6. **Payoff engine** — calculates net credit, maximum profit, maximum loss, breakevens, and expiration payoff for arbitrary supported legs.
7. **Liquidity and fill model** — rejects unusable chains and simulates conservative multi-leg limit fills without assuming midpoint execution.
8. **Risk governor** — enforces all trade, daily, timing, freshness, product, and paper-only controls in code.
9. **Portfolio selector** — ranks eligible structures and chooses at most two while checking correlated exposure.
10. **Paper ledger** — durably records cycles, evidence, candidates, orders, fills, positions, exits, P&L, and model versions.
11. **Dashboard/reporting** — renders the standalone executive UI and detailed QA evidence.
12. **AI CIO adapter** — publishes the `OPTION-001 / 0DTE_OPTIONS` read-only summary contract and dashboard link.

AI-generated prose may explain a decision but may not create facts, change scores, select unverified contracts, or override code-enforced gates.

## 5. Data sources and safety boundary

Alpaca is the primary Version-1 source for market status, underlying data, option contracts, chains, quotes, implied volatility, and Greeks. Public authoritative sources may supplement economic and corporate-event checks.

Server secrets are injected through environment variables and never committed:

- `APCA_API_KEY_ID`
- `APCA_API_SECRET_KEY`
- `APCA_API_BASE_URL=https://paper-api.alpaca.markets`

Market-data routing is distinct from the paper-order endpoint. Configuration must refuse a non-paper trading base URL. Startup fails closed if paper-only status cannot be proven.

The ChatGPT Alpaca connection is useful for interactive market research but is not the deployed bot's credential or execution channel.

## 6. Daily schedule

All times are U.S. Eastern Time and exchange-calendar aware.

- **09:30:** Start the session cycle, collect opening data, and begin the opening-range window.
- **09:45–10:30:** Evaluate and submit qualifying paper entries.
- **After 10:30:** Manage existing positions only; no new entries.
- **Continuous during positions:** Refresh underlying evidence, option quotes, risk, thesis, and exit gates.
- **15:30:** Mandatory close deadline for every Version-1 position.

The scheduler uses idempotency keys based on trade date, strategy identity, cycle, symbol, and structure. Restarts reconstruct state from the durable ledger and cannot duplicate orders or positions.

## 7. Evidence model

Each candidate receives three independently reported scores.

### Direction evidence

Evidence includes VWAP position/slope, EMA(9)/EMA(20) alignment, 15-minute structure, 5-minute confirmation, opening-range behavior, ADX, relative volume, gap behavior, SPY/QQQ confirmation, and relevant sector alignment.

### Range evidence

Evidence includes VWAP flatness, CHOP, ADX, realized volatility, opening-range containment, expected-move position, support/resistance, recent intraday behavior, and event status.

### Premium evidence

Evidence includes implied volatility, realized volatility, IV/realized-volatility relationship, credit-to-width ratio, maximum-loss efficiency, delta, gamma, bid/ask quality, displayed size, volume, open interest, and estimated slippage.

The system explicitly distinguishes:

- **Evidence confidence:** deterministic model score
- **Market-implied probability:** option-derived information such as delta-based estimates
- **Calibrated probability:** empirical probability produced only by a validated calibrated model

An unvalidated score must never be labeled as a historical win probability.

Every score stores component values, weights, data timestamps, source provenance, gate results, and model version. Weight changes require versioning and replay/backtest comparison; they may not rewrite historical decisions.

## 8. Expected move

The baseline market-implied move uses current same-expiration ATM option midpoints:

`ATM straddle = ATM call midpoint + ATM put midpoint`

`expected lower boundary = current underlying price - ATM straddle`

`expected upper boundary = current underlying price + ATM straddle`

The output describes this as an implied estimate through expiration, not a guaranteed range. Alternative methods must be named, versioned, and kept separate from the ATM-straddle calculation.

## 9. Hard eligibility gates

A candidate cannot enter ranking when any required gate fails:

- Market is not open or product is not currently tradable
- No confirmed same-day expiration
- Unknown settlement, exercise, multiplier, or expiration behavior
- Stale, crossed, incomplete, or unusably wide quotes
- Missing required Greeks or underlying data
- Insufficient tradable size or liquidity
- Imminent unaccepted economic, Federal Reserve, earnings, company, halt, or binary-event risk
- Incomplete opening evidence
- Structure exceeds the per-trade maximum defined loss
- Proposed entry is outside the approved time window
- Paper-only configuration cannot be proven
- Daily entry count or daily risk limit is exhausted

Gate thresholds are configuration values with explicit defaults, validation, and evidence output. No missing value silently passes.

## 10. Structure routing

The routing priority is:

1. **Iron condor or iron butterfly** when range evidence is strong, realized movement is controlled, event risk passes, and premium adequately compensates for risk.
2. **Put credit spread** when bullish directional evidence is strong and premium/liquidity pass.
3. **Call credit spread** when bearish directional evidence is strong and premium/liquidity pass.
4. **WATCH or NO_TRADE** when evidence conflicts or no structure meets all gates.

Low realized volatility alone does not justify an iron condor or butterfly; implied premium must remain adequate. High premium alone does not justify a directional spread when it results from unsafe events, illiquidity, or uncontrolled price movement.

Short-strike delta near 0.10–0.15 is a preferred search region, not a guaranteed probability or mandatory strike. Short strikes should also sit beyond meaningful technical boundaries when possible. Wing widths are selected from available strikes and risk limits rather than assumed to be fixed across products.

### 10.1 Optimal delta selection

The bot does not treat one fixed delta as optimal. On every evaluation cycle it enumerates available structures across a configurable short-delta ladder, initially centered on absolute deltas `0.08`, `0.10`, `0.12`, `0.15`, `0.18`, and `0.20`. It may inspect candidates up to approximately `0.25` only when directional evidence is exceptionally strong. Availability of a target delta does not allow a candidate to bypass technical, liquidity, event, payoff, or risk gates.

For directional verticals, the selected short strike must maximize risk-adjusted expected value among candidates that pass all gates. For iron condors, put-side and call-side deltas may differ when evidence is directionally skewed; the system must not force symmetric deltas when the market evidence is asymmetric.

Before scoring, each delta candidate is rejected if it:

- Sits inside an unsafe technical support/resistance boundary
- Has inadequate clearance from the applicable expected-move boundary
- Exceeds the $100 maximum defined loss for one contract
- Provides inadequate credit relative to spread width and maximum loss
- Has stale, crossed, excessively wide, incomplete, or insufficiently sized quotes
- Has unacceptable gamma exposure for the remaining holding period
- Fails event, product, timing, or paper-only gates

For every surviving candidate, the probability engine estimates distinct outcomes rather than relying on short-option delta alone:

- Probability of finishing beyond the short strike at the mandatory exit horizon
- Probability of touching the short strike before 15:30 ET
- Probability of reaching the 50%-of-maximum-loss exit
- Probability of reaching the 50%-of-credit profit target
- Probability of remaining inside both short strikes for a neutral structure
- Distribution of underlying prices and spread values at the mandatory exit

Delta is stored as a market risk input and a rough market-implied approximation, never as a guaranteed probability. Touch probability must not be represented by an unvalidated shortcut such as mechanically doubling delta.

Candidate expected value is computed over the mutually exclusive modeled exit outcomes:

`expected value = sum(probability(outcome) × net P/L(outcome)) - estimated slippage - estimated fees`

The calculation includes profit-target, thesis-invalidation, underlying-boundary, loss-stop, time-exit, and adverse-slippage outcomes. The model must report its probability source, horizon, version, assumptions, and residual probability treatment so that the values sum consistently.

The optimal-delta score combines:

- Expected value after modeled costs
- Credit and maximum-profit efficiency relative to maximum loss
- Clearance beyond technical and expected-move boundaries
- Liquidity and realistic multi-leg execution quality
- Gamma safety for time remaining
- Modeled short-strike touch and loss-stop probability
- Symbol-, structure-, time-, weekday-, and regime-specific Experience Learner evidence

The selected delta is the highest-scoring candidate that passes every hard gate. It is not automatically the lowest delta or the candidate with the largest premium. The ledger preserves the full delta ladder and rejection/score evidence, not only the winner.

Iron-butterfly selection uses a different parameterization. Its short body is chosen near the model's expected landing zone using expected close, VWAP/opening-range equilibrium, high-volume price area, technical convergence, and validated symbol-specific pinning evidence. Its short legs may therefore be near `0.50` absolute delta. Wings are then enumerated from available strikes, subject to the $100 maximum defined loss, payoff, liquidity, and fill gates. A butterfly is rejected when its modeled profitable range is too narrow for the predicted price distribution.

The Experience Learner tracks realized finish, touch, stop, target, slippage, and expected-value accuracy for every evaluated delta. Delta preferences remain versioned by symbol, structure, time, weekday, and volatility regime. Learned delta selection first runs in shadow mode and may influence active ranking only after the model-promotion requirements in Section 14 are satisfied.

## 11. Daily ranking and portfolio selection

The dashboard ranks every governed symbol or records why it was not rankable. It separately identifies the best neutral and best directional candidates.

Final selection uses evidence score, premium efficiency, liquidity, event safety, payoff, risk, and portfolio correlation. It selects zero, one, or two trades. Two highly correlated positions cannot be selected accidentally; the selector must report correlation/exposure evidence and either reject the second position or explicitly justify it within the $200 daily cap.

Every selected trade records why it outranked alternatives. Every rejected candidate records the exact gates or score deficiencies that prevented selection.

## 12. Paper entry and fill model

All structures enter as complete multi-leg limit orders. The bot does not leg into a position.

An entry requires fresh, non-crossed quotes for all legs, acceptable liquidity, and evidence that the combined order could realistically trade. The ledger records natural price, midpoint, proposed limit, quote timestamps, displayed size, and estimated slippage.

The model never assumes a midpoint fill. It uses a conservative documented fill rule that can be replayed. An order may improve its limit only within configured bounds while its original evidence remains valid. It expires unfilled at 10:30 or earlier when the thesis, quotes, or gates fail.

Partial simulated fills are cancelled/reconciled as an incomplete structure and may not be represented as a valid defined-risk position.

## 13. Risk and exit governance

### Portfolio limits

- Maximum defined loss per trade: **$100**
- Maximum combined daily defined loss: **$200**
- Maximum new positions per trading day: **2**
- Contracts are sized by maximum possible loss, never premium alone
- A structure that cannot fit one contract within $100 is rejected

### Exit hierarchy

1. Emergency data-integrity handling
2. Thesis invalidation
3. Underlying boundary, support/resistance, breakeven, or short-strike rule
4. Active loss exit when open loss reaches **50% of the position's maximum possible loss**
5. Daily-risk stop
6. Default profit management near **50% of original credit**, subject to later evidence-based optimization
7. Mandatory exit by **15:30 ET**

The $100 value is maximum defined exposure, not the intended loss. A 50%-of-max-loss exit targets approximately $50 or less, but the ledger must record actual simulated slippage and may not claim the stop price is guaranteed.

Version 1 never intentionally holds a position through expiration. Product-specific assignment, exercise-by-exception, pin, after-hours, settlement, broker-liquidation, and cutoff risks remain visible in the evidence.

## 14. Experience Learner

The Experience Learner uses numerical evidence, market data, options data, and technical indicators to make decisions from Day 1 while continuously observing outcomes.

For every selected and rejected candidate it records prediction, realized direction, range containment, expected-move behavior, structure outcome, premium captured, maximum favorable excursion, maximum adverse excursion, exit effectiveness, fill realism, volatility regime, weekday, time, gap state, market/sector state, event state, and model version.

Experience profiles are maintained by symbol, product type, structure, volatility regime, weekday, and time window. They provide auditable historical context to the active deterministic model.

After sufficient history exists, statistical or machine-learning models run in shadow mode. Shadow output cannot influence selection until it demonstrates:

- A documented minimum sample size appropriate to the model and stratification
- Probability calibration
- Walk-forward performance
- Untouched out-of-sample improvement over the deterministic baseline
- Positive expectancy after modeled fees and slippage
- Acceptable drawdown
- Stability across multiple volatility regimes
- Reproducible versioned results

Promotion requires an explicit governance decision and preserves the prior baseline. A promoted model still cannot override event, liquidity, freshness, paper-only, sizing, daily-risk, or time gates.

## 15. Dashboard

The standalone dashboard follows the Swing and Dividend Bot design language and provides:

- Market-session status, schedule phase, VIX, SPY/QQQ, events, and freshness
- Complete 12-symbol leaderboard
- Best neutral and best directional candidates
- Up to two selected trade tickets with every leg and payoff metric
- Open positions with live paper P&L and distance to risk boundaries
- Completed trades with entry/exit evidence and outcome grading
- Experience Learner analysis by symbol, structure, regime, and probability bucket
- Rejected candidates and exact reasons
- Data, scheduler, ledger, risk, and paper-only health

Tables must support QA drill-down without overwhelming the executive view. Every displayed decision links to its immutable evidence record.

## 16. AI CIO contract

Trade-Option-Bot owns detailed option research, paper execution, monitoring, and reports. It publishes a small read-only contract for `OPTION-001 / 0DTE_OPTIONS` containing:

- Module and paper-only status
- Session phase
- Eligible candidate count
- Open paper-position count
- Daily realized and open P&L
- Daily risk used and remaining
- Best-ranked opportunity
- Data freshness
- Health status and blocking reasons
- Standalone dashboard URL

The main AI CIO renders the module and a View link. AI CIO integration must not directly mutate Trade-Option-Bot's ledger or bypass its governance.

## 17. Persistence and auditability

The ledger must preserve raw-source references or permitted snapshots, normalized observations, derived indicators, score components, gates, candidate structures, proposed orders, simulated fills, positions, exits, P&L, explanations, scheduler runs, configuration hashes, and model versions.

Records are append-oriented. Corrections create explicit superseding records rather than silently rewriting prior evidence. All timestamps include timezone and source timestamp. Reports indicate stale or unavailable evidence honestly.

## 18. Failure behavior

- Alpaca unavailable: block new entries and mark the cycle `DATA_UNAVAILABLE`
- Missing or stale chain: reject affected candidates
- Missing Greeks: reject the affected structure
- Stale underlying: freeze new entries and apply conservative position handling
- Event source unavailable: fail the event gate unless a configured authoritative fallback succeeds
- Restart: restore positions and risk state from the ledger
- Duplicate invocation: return the existing idempotent result
- Partial/inconsistent ledger: enter safe mode and prohibit new entries
- Dashboard/report failure: trading logic remains paper-only and auditable; health becomes degraded

## 19. Test and acceptance requirements

Automated tests must demonstrate:

- No live endpoint or real-order path can execute
- Startup rejects a non-paper Alpaca base URL
- Maximum loss cannot exceed $100 per trade
- Daily risk cannot exceed $200
- More than two daily entries are rejected
- Entry cannot occur outside 09:45–10:30 ET
- All positions receive a close action by 15:30 ET
- Stale/incomplete chains and missing Greeks cannot pass
- Vertical, condor, butterfly, and arbitrary-leg payoff math is correct
- Equity and index settlement metadata is not conflated
- Conservative fill rules do not assume midpoint fills
- Duplicate cycles cannot duplicate trades
- Restart reconstructs ledger and risk state
- Every ranking, selection, and rejection has complete evidence
- Probability labels distinguish confidence, market-implied, and calibrated values
- AI prose cannot override risk gates or create market facts
- Correlation controls evaluate the second daily trade
- Dashboard and AI CIO contracts render and validate
- Wheel lifecycle is not accidentally activated in Version 1

Acceptance requires a supervised paper-only deployment on `ai-cio-platform`, successful market-data and paper-endpoint health checks, a completed dry run with orders disabled, and then explicit approval before paper-order simulation is enabled.

## 20. Repository and deployment direction

The GitHub repository will be private and named `Trade-Option-Bot`. Implementation should follow relevant Python packaging, testing, service, reporting, navigation, and deployment conventions observed in the existing `Trade-Swing-Bot` and `Trade-Dividend-Bot`, while keeping this module independent.

Deployment target: `/home/tradebot/Trade-Option-Bot` on `ai-cio-platform`.

No changes to either existing bot are implied by this specification. Any later main AI CIO navigation change requires a separately reviewed, minimal integration step.

## 21. Explicit non-goals for Version 1

- Live brokerage execution
- Robinhood order placement
- Wheel trades or stock assignment handling
- Naked short options
- Legging into multi-leg positions
- Holding positions intentionally through expiration
- Self-modifying risk limits
- Unreviewed model promotion
- Fabricated or silently substituted market data
- Guaranteed-profit, guaranteed-fill, or guaranteed-probability claims
