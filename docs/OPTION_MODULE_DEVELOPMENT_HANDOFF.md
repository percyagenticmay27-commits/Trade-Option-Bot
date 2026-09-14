# Trade Option Bot — Development Handoff

## Copy this prompt into a new chat

Continue development of the standalone `Trade-Option-Bot` repository.

Repository: `https://github.com/percyagenticmay27-commits/Trade-Option-Bot.git`

Working branch: `feature/option-001-foundation`

Local working directory used by the previous development session:
`/workspace/scratch/cb8984e0c503/Trade-Option-Bot`

Read these files first:

1. `docs/OPTION_MODULE_DEVELOPMENT_HANDOFF.md`
2. `docs/specs/2026-09-13-trade-option-bot-0dte-design.md`
3. `docs/plans/2026-09-13-trade-option-bot-0dte-implementation.md`
4. `progress.md`

Continue the written plan inline from the first incomplete task. Use test-driven development, run the focused tests and entire suite, update `progress.md`, update this handoff after every major task, commit to the feature branch, and sync the GitHub branch. Give the user a review and total completion percentage after each major task.

Do not enable live trading. The system must remain paper-only and accept only the exact Alpaca paper endpoint `https://paper-api.alpaca.markets`. Never send a real order, expose credentials, invent market data, silently replace an unsupported symbol, retry an uncertain order submission, or allow shadow learning to affect rankings before calibration and out-of-sample validation pass.

## Final goal

Build and verify Version 1 of AI CIO options module `OPTION-001`, strategy type `0DTE_OPTIONS`, with the same dashboard look and feel as the Swing and Dividend bots and a View link in the AI CIO platform. It must evaluate the governed symbol universe daily, select zero to two evidence-backed paper trades, prefer high-quality condors or butterflies in range regimes, use directional credit spreads only with strong direction evidence, manage positions conservatively, and maintain a symbol-specific Experience Learner in shadow mode. Deployment to `/home/tradebot/Trade-Option-Bot` on `ai-cio-platform` occurs only after GitHub development is complete and verified.

Wheel strategies are reserved for a later, separately governed `WHEEL_OPTIONS` engine and are not enabled in Version 1.

## Governed Version 1 constraints

- Symbols: `NVDA`, `GOOGL`, `AAPL`, `MSFT`, `AMZN`, `META`, `AVGO`, `TSLA`, `XSP`, `MRUT`, `MBTX`, `DJX`
- Explicit exclusions: `GLDM`, `SSRM`, `ETH`, `XME`, `GDX`, `MNMD`
- Maximum defined loss: `$100` per trade and `$200` per day
- Maximum new paper entries: `2` per day; zero is valid
- Entry window: `09:45–10:30 ET`
- Mandatory exit: normally by `15:30 ET`
- Default profit management: approximately 50% of original credit
- Active loss exit: 50% of maximum possible loss or earlier thesis/underlying invalidation
- Multi-leg orders only; never leg into a position
- Experience Learner stays shadow-only until proven calibrated and better out-of-sample

## Completed work

- Task 1 — paper-only foundation and immutable domain/configuration contracts
- Task 2 — exact Decimal payoff engine and non-bypassable risk governor
- Task 3 — fail-closed Alpaca market-data, paper-broker, normalization, and event-provider boundaries
- Task 4 — indicators, versioned evidence scoring, and deterministic Day-1 Experience Learner
- Task 5 — structure enumeration, governed delta ladder, probability contracts, and expected-value delta optimizer
- Task 6 — durable audit ledger, conservative fill model, and position lifecycle
- Task 7 — deterministic daily orchestration, portfolio selection, and isolated shadow learning

Current completion: **70% of the 10-task Version 1 implementation plan**.

## Current stopping point

Task 7 is complete. The focused Task 7 suite has 11 passing tests, the entire repository has 86 passing tests, and `git diff --check` passes.

**Task 8 is in progress and blocked only on browser-based rendered verification.** The JSON-first report builder, standalone dashboard renderer, template, CSS, client-only symbol filter, CLI report generation, five focused tests, and five generated artifact types are implemented. The exact CLI command succeeds after editable installation. A render capture was attempted at 375px, 720px, and 1280px, but the provided capture tool reported: `No installed Chrome, Chromium, or Edge executable was found.` Do not claim visual, interaction, console-error, or responsive verification until a browser-capable environment runs those checks.

Next action: run the frozen render checklist from `/workspace/scratch/cb8984e0c503/task8-ui-direction.md` in a browser-capable environment. Verify 375x812, 720x900, and 1280x800; keyboard-open an evidence details control; type `AAPL` in the labeled symbol filter and assert only AAPL remains; confirm no console errors or external requests. If those checks pass, run the focused and full Python suites, mark Task 8 complete in `progress.md`, update this handoff to 80%, commit, and sync GitHub. If the render exposes a defect, repair it before completing Task 8.

The Task 8 implementation is preserved as an explicit checkpoint commit on the feature branch, but Task 8 is not marked complete because rendered verification has not passed.

## Important Task 7 behavior

- Every entry-window cycle produces the governed 12-symbol leaderboard in stable ordering.
- Provider failure produces `DATA_UNAVAILABLE` evidence for every affected symbol instead of a manufactured candidate.
- Market-closed and pre-entry cycles do not select trades.
- Cycles after 10:30 ET switch to management mode; 15:30 ET emits the mandatory-exit window.
- Portfolio selection allows zero, one, or two candidates and honors the $200 daily aggregate loss ceiling.
- The best neutral candidate is considered alongside the best qualified directional candidate.
- Same-exposure candidates are rejected with `CORRELATED_EXPOSURE` unless a documented justification flag is present.
- Cycle records are persisted before paper submission and duplicate cycle IDs are idempotent across process restarts.
- Shadow predictions are stored but cannot alter active scores.
- Shadow promotion cannot be enabled by runtime configuration; it requires offline proof and a code release.
- CLI defaults to the read-only `health` command; state-changing paper operations require explicit commands.

## Important Task 6 behavior

- SQLite audit records are append-oriented and written inside transactions.
- Each record type uses a unique idempotency key so process restarts do not duplicate records.
- Corrections append new records and reference the superseded record; history is not overwritten.
- Records retain canonical payloads, configuration/model hashes, source timestamps, and full rejected-delta evidence.
- The paper fill model never assumes a midpoint fill.
- A fill occurs only when the complete multi-leg natural market reaches the limit; improvement cannot exceed midpoint.
- An incomplete multi-leg quote is rejected and an unfilled entry expires after 10:30 ET.
- Open positions exit for profit, thesis failure, underlying invalidation, 50% of maximum possible loss, daily stop, or the 15:30 ET mandatory exit.
- Missing option data creates `DEGRADE`, never zero P&L or a false successful exit.
- Underlying invalidation remains active while option valuation is degraded.

## Important Task 5 behavior

- Base short-delta candidates: `0.08`, `0.10`, `0.12`, `0.15`, `0.18`, `0.20`
- `0.25` is conditional on strong directional evidence and explicit configuration
- Every attempted delta is preserved with acceptance or stable rejection reason codes
- Delta is a candidate-selection input, not a probability guarantee
- Touch probability is an independent versioned input; no `2 × delta` shortcut exists
- Exact payoff math enforces the `$100` maximum-loss gate
- Technical and expected-move boundaries, gamma, liquidity, protective-wing availability, and credit are hard gates
- Neutral regimes can produce asymmetric iron condors
- Butterfly body is derived from the expected landing zone rather than the vertical delta ladder
- Expected value is calculated from mutually exclusive outcomes, slippage, and fees
- Experience adjustments contribute zero unless an explicit validation flag is true

## Verification commands

```bash
cd /workspace/scratch/cb8984e0c503/Trade-Option-Bot
.venv/bin/pytest tests/test_orchestrator.py tests/test_portfolio.py tests/test_shadow.py -q
.venv/bin/pytest -q
git status --short
```

Expected at this checkpoint: 11 focused tests and 86 full-suite tests pass.

## Git and safety notes

The shell checkout cannot authenticate directly to the private GitHub repository. Previous tasks were committed locally and mirrored to the GitHub feature branch through the connected GitHub plugin by creating a full tree, creating a commit whose parent is the prior remote feature-branch commit, and advancing the branch ref without force. Do not overwrite `main`, force-update the branch, or include credentials.
