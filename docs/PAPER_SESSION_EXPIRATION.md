# Paper session expiration

The local paper runtime expires positions once all held legs reach their expiration-date New York regular-session close, using exchange-calendars XNYS (including early closes). This lifecycle step precedes quote validation on scans, management, and close-all-paper. It is idempotent and retains exact entry fills, legs, and risk history.

Expired positions move from open to completed with status EXPIRED and exit_pending=false. No market fill is invented: exit_fills=[], realized_pnl=null, settlement_status=PENDING until authoritative expiration payoff evidence is reconciled. Only known realized P/L contributes to booked totals; settlement_pending_count is exposed in positions and summary.

2026-11-03: all 329 tests passed (four upstream NumPy/calendar deprecation warnings). The live SPX condor PAPER-0e6d9fba1645d1dcd8758b87 was reconciled at 16:12 ET, effective expiry 16:00 ET, with no broker submission. The prior ledger and reports are backed up in results/expiry_reconciliation_backup_20261103T151211.

## Close-time trigger deployment status

scripts/reconcile_session_expiration.py runs management only if an open position has actually expired. deploy/user-systemd/option-paper-expiration.service and .timer are validated USER units; they check both 13:00 and 16:00 New York, and the exchange calendar prevents premature expiration on regular or holiday sessions.

Timer activation is NOT complete: Remote Desktop Commander's allowed-write boundary rejected /home/tradebot/.config/systemd/user. No alternate mechanism was used to bypass that boundary. Existing schedules were not changed. Runtime expiration already operates on every subsequent bot cycle.

From an authorized tradebot user session, install via:
    systemctl --user link /home/tradebot/Trade-Option-Bot/deploy/user-systemd/option-paper-expiration.service /home/tradebot/Trade-Option-Bot/deploy/user-systemd/option-paper-expiration.timer
    systemctl --user enable --now option-paper-expiration.timer

No credentials, live trading, broker permissions, entry gates, or intraday exits were changed.

## November 19, 2026: Barney verified PM expiration and EOD reconciliation

The local paper ledger expiration sweep is now paired with `scripts/barney_post_session.py`, `src/option_bot/post_session.py`, `deploy/user-systemd/barney-post-session.service` and `.timer`. A service invocation first calls the usual `manage-once` risk manager in no-entry mode (baseline and separate shadows); it then independently checks **every remaining 0DTE/expired baseline open leg** with the XNYS session calendar and moves any expired positions from open to `EXPIRED` without inventing fills. An expiration cannot be represented as a sale; `exit_fills=[]`.

For **SPX European PM cash-settled** contracts only, the reconciler retrieves Cboe's exchange-published `^SPX` daily closing level at `https://cdn.cboe.com/api/global/delayed_quotes/charts/historical/_SPX.json`, requires the **exact expiration date**, and independently computes every put/call leg's intrinsic cash payoff. The proof is retained with the position and the `PAPER_CASH_SETTLE` event. The resulting status `RECONCILED_CBOE_CLOSE` is **paper settlement based on Cboe's published closing index**, not confirmation that the broker has cleared a cash transfer. Other products or missing exchange close data remain `PENDING` with a named error, no invented profit or filled broker order. The scheduled retries must continue until data is supplied.

`results/barney_end_of_day.json` explicitly separates `executed_closing_trades_today` from `cash_settled_expirations_today`, lists unresolved settlements, current open count, source provenance and cumulative paper realized P/L. The runner also refreshes `option_001_positions.json` and `option_001_summary.json`. In live trading, the broker owns exercise and settlement; this code **does not send actual Robinhood close orders**, and a delayed post-close sweep cannot execute an option sale once the market has closed. Before any live transition, broker position synchronization and intraday actual-close capabilities must be separately implemented and verified.

The new user service timer has 13:02 ET early-close check, 16:02 ET normal post-close check, and 16:20/17:05 ET reconciliation retries. Always confirm its user-systemd active/enabled status, rather than assuming the repository unit file is installed.
