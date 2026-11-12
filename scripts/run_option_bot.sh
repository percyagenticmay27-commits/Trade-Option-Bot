#!/usr/bin/env bash
set -euo pipefail

APP_ROOT=/home/tradebot/Trade-Option-Bot
LOCK_FILE=/run/user/$(id -u)/trade-option-bot.lock
COMMAND=${1:-health}
export ROBINHOOD_RESEARCH_SNAPSHOT_PATH="${ROBINHOOD_RESEARCH_SNAPSHOT_PATH:-$APP_ROOT/results/robinhood_option_research.json}"
if (( $# )); then
  shift
fi

case "$COMMAND" in
  coverage-once|events-once|scan-once|manage-once|close-all-paper|render-reports|health) ;;
  *) echo "CONFIG_UNAVAILABLE: unsupported option bot command" >&2; exit 64 ;;
esac

if [[ ! -x "$APP_ROOT/.venv/bin/python" || ! -r "$APP_ROOT/configs/option-001.json" ]]; then
  echo "CONFIG_UNAVAILABLE: installation or governed configuration is missing" >&2
  exit 78
fi

if [[ "$COMMAND" == "scan-once" ]]; then
  # Fresh completed bars with conflicting trend evidence are a WAIT, not
  # a broken connector. No new-entry scan; still manage existing positions.
  set +e
  "$APP_ROOT/.venv/bin/python" -m option_bot.direction_wait \
      "$APP_ROOT/results/option_001_collection_plan.json" \
      --output "$APP_ROOT/results/option_001_direction_wait.json"
  WAIT_RC=$?
  set -e
  if [[ "$WAIT_RC" == "10" ]]; then
    SHADOW_EARLY_ENTRY_SCAN=1 exec "$APP_ROOT/scripts/run_option_bot.sh" manage-once
  fi
  if ! "$APP_ROOT/.venv/bin/python" -m option_bot.research_gate \
      "$ROBINHOOD_RESEARCH_SNAPSHOT_PATH" --max-age-seconds 60; then
    "$APP_ROOT/.venv/bin/python" -m option_bot.refresh_queue scan-once \
      FRESH_ROBINHOOD_SNAPSHOT_REQUIRED --output-dir "$APP_ROOT/results"
    echo "PENDING_CONNECTOR_REFRESH: fetch Robinhood data and publish before scan-once" >&2
    exit 66
  fi
fi

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "OPTION-001 cycle already running" >&2
  exit 75
fi

cd "$APP_ROOT"
exec "$APP_ROOT/.venv/bin/python" -m option_bot.cli "$COMMAND" --config "$APP_ROOT/configs/option-001.json" "$@"
