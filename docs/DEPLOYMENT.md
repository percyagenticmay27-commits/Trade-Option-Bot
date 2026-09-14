# OPTION-001 paper-only deployment

Do not deploy from an unreviewed branch and do not configure a live broker URL.

## Install as `tradebot`

```bash
cd /home/tradebot
git clone https://github.com/percyagenticmay27-commits/Trade-Option-Bot.git
cd Trade-Option-Bot
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q
```

Create `/etc/trade-option-bot.env` with the paper credentials and these fixed values:

```text
APCA_API_BASE_URL=https://paper-api.alpaca.markets
OPTION_BOT_TIMEZONE=America/New_York
OPTION_BOT_DB_PATH=/home/tradebot/Trade-Option-Bot/results/option_bot.sqlite3
```

Never place credentials in the repository, shell history, unit files, screenshots, or reports. The environment file must be owned by root, readable by `tradebot`, and mode 600. A server administrator should review and run:

```bash
sudo chown root:tradebot /etc/trade-option-bot.env
sudo chmod 600 /etc/trade-option-bot.env
```

Run migrations by starting read-only health, then generate an order-disabled dry run. Do not enable paper submission until the health report, all 12 symbol coverage results, dashboard, AI CIO contract, and candidate/rejection ledger have been reviewed.

## Service installation

Root access is deliberately not assumed. After reviewing the units, the operator may run:

```bash
sudo cp deploy/systemd/trade-option-bot-* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now trade-option-bot-dashboard.service
```

Do not enable scan, manage, or close timers until the dry-run approval gate is complete.

## Rollback

Stop and disable the option timers and dashboard, retain the SQLite ledger and reports, return to the last reviewed Git commit, recreate the virtual environment, rerun tests and health, then restart only the read-only dashboard. Never delete the audit database during rollback.

Rotate Alpaca paper credentials by stopping option services, replacing the protected environment file, rerunning health, and then restarting approved paper services. Credential rotation must not change the endpoint.
