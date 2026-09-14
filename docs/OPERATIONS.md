# OPTION-001 operations

The systemd timers are wake-up mechanisms only. Application gates are authoritative for the U.S. Eastern session, exchange calendar, entry window, daily entry/risk limits, duplicate-cycle protection, and mandatory exit.

## Routine checks

```bash
cd /home/tradebot/Trade-Option-Bot
.venv/bin/python -m option_bot.cli health --config configs/option-001.json
sudo systemctl status trade-option-bot-dashboard.service
sudo journalctl -u 'trade-option-bot-*' --since today
```

`CONFIG_UNAVAILABLE` is a hard stop. Do not work around missing credentials, a non-paper endpoint, an unwritable database, unavailable event evidence, or unsupported option products.

The scan cadence may wake after 10:30 ET, and the management cadence may wake outside regular trading hours. Those invocations must exit without entry because the application exchange-calendar and time gates remain authoritative.

## Incident handling

- Unknown paper-order result: do not retry; reconcile by client order ID.
- Stale options: block entries; mark open positions degraded and keep underlying invalidation active.
- Event source unavailable: block entries.
- Dashboard/report mismatch: disable entry timers, retain evidence, regenerate read-only reports.
- Risk-limit mismatch: disable all option timers and preserve the ledger.

The 15:25 ET close timer starts mandatory close enforcement before the 15:30 ET governance deadline. Broker acceptance or fill is not guaranteed; unresolved positions require operator reconciliation before the closing bell.
