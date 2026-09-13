# Trade-Option-Bot

Paper-only, evidence-driven options research and simulation module for the AI CIO platform.

## Safety boundary

- Module: `OPTION-001`
- Initial strategy: `0DTE_OPTIONS`
- Paper endpoint only: `https://paper-api.alpaca.markets`
- No Robinhood execution
- No live brokerage execution
- No real orders or capital movement
- Maximum defined loss: $100 per trade and $200 per day
- Maximum two new paper positions per trading day

The application fails closed when paper mode, credentials, product metadata, or required evidence cannot be verified.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/pytest -q
```

Copy `.env.example` to a protected server environment file and supply paper credentials there. Never commit credentials.
