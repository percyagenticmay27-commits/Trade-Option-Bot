# OPTION-001 Barney — experimental defensive opposite-side credit spread

**Authorized:** November 11, 2026. **MODE: PAPER-ONLY.**

## Scope and authority

This is exactly **one** defensive adjustment type. The existing 11:00 a.m.
Central cutoff still applies to **new standalone** paper entries. The special
**10:00–12:30 p.m. Central (exclusive)** window applies ONLY to an already open,
market-adverse 0DTE SPX/XSP defined-risk credit vertical. The 50%-maximum-risk
loss stop stays active; no real orders, broker buying power or account holdings.

The existing local paper manager used by `manage-once` evaluates the defense
before its original exit decision only if current realized? **No:** the trigger
is **unrealized mark-to-market loss** of at least 20% but less than 50% of the
*original* trade's maximum loss. If a stop is already triggered it closes as
usual, without trying to rescue it. No early expiration hold exemption is
introduced. The pre-existing mandatory close, event/quote safeguards and
position limits remain.

The manager may sell ONE short option on the **opposite** side, delta <=0.20
in absolute value, while buying a farther-out wing of the same width as the
original vertical. It becomes a four-legged non-overlapping iron condor.
New credit must be at least $0.10/share of index exposure (e.g. $10 at 100x).
Every leg needs an independently timestamped fresh option quote, valid
bid/ask sizes, matching chain/instrument identity and verified cash/European
PM-settled 0DTE metadata. Simulation opens the new short at **bid** and the
new long at **ask**, not the midpoint. No fill if those data are missing.

The prospective resulting structure is priced and verified *before* mutating
the persistent paper ledger. Its total maximum loss **must not exceed either
the original risk or the configured per-trade/daily limit**; if the potential
combined payoff does not improve maximum loss, do not adjust. Only one
adjustment is permitted per position, with an immutable
`PAPER_DEFENSIVE_ADJUST` event and itemized fills, premium and risk before/after.
Once adjusted, normal defined-risk stop management and expiration continue.

## Evidence, risks and practical limits

This adjustment does **not** erase already accrued mark-to-market losses and
may itself worsen final P/L if the market reverses. Modelled transaction
costs currently include bid/ask crossing but **not brokerage fees or
exchange commissions**. A credit spread on the other side is not guaranteed
to be available, profitable, or better than immediately closing.

This is an experiment, not a promise of recovery. Compare each actual
paper adjustment's net results against the original 50% loss exit baseline;
record false positives, additional fills, maximum adverse excursion, and
increased expense. These counterfactuals need distinct forward data and
must never be inferred from the eventual result alone.

## Implementation status

- `src/option_bot/defensive_condor.py`: sole strategy gate.
- `src/option_bot/local_paper.py`: active `manage-once` paper-state lifecycle.
- `configs/barney.json`: defensive policy declaration. **Independent
  `barney_alpaca.py` standalone daemon remains not activated**; do not claim
  it is running.
- Read-only Robinhood management automation: ask for actual candidate
  opposite-side quotes *only* for qualifying held spreads before 12:30 CT.
- `tests/test_defensive_condor.py`: unit and local-manager integration tests.

No historical trade was retroactively adjusted. Today November 11 the
OPTION-001 ledger had no open position at the time this was deployed.
