#!/usr/bin/env bash
set -euo pipefail

APP_ROOT=/home/tradebot/Trade-Option-Bot
LOCK_FILE=/run/user/$(id -u)/trade-option-bot.lock
COMMAND=${1:-health}
if (( $# )); then
  shift
fi

case "$COMMAND" in
  coverage-once|scan-once|manage-once|close-all-paper|render-reports|health) ;;
  *) echo "CONFIG_UNAVAILABLE: unsupported option bot command" >&2; exit 64 ;;
esac

if [[ ! -x "$APP_ROOT/.venv/bin/python" || ! -r "$APP_ROOT/configs/option-001.json" ]]; then
  echo "CONFIG_UNAVAILABLE: installation or governed configuration is missing" >&2
  exit 78
fi

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "OPTION-001 cycle already running" >&2
  exit 75
fi

cd "$APP_ROOT"
exec "$APP_ROOT/.venv/bin/python" -m option_bot.cli "$COMMAND" --config "$APP_ROOT/configs/option-001.json" "$@"
