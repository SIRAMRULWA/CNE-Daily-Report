#!/usr/bin/env bash
set -euo pipefail

cd /app

SOURCE="${PIPELINE_SOURCE:-helix}"
PERIOD="${HELIX_PERIOD:-}"
PIPELINE_TIMEZONE="${WORKSPACE_TIMEZONE:-Africa/Johannesburg}"
WEEKDAYS_ONLY="${PIPELINE_WEEKDAYS_ONLY:-false}"

if [[ "${WEEKDAYS_ONLY,,}" =~ ^(1|true|yes|on)$ ]]; then
  DAY_OF_WEEK="$(TZ="$PIPELINE_TIMEZONE" date +%u)"
  if [ "$DAY_OF_WEEK" -ge 6 ]; then
    echo "Pipeline skipped: weekend in $PIPELINE_TIMEZONE ($(TZ="$PIPELINE_TIMEZONE" date +%Y-%m-%d))"
    exit 0
  fi
fi

if [ "$SOURCE" = "helix" ]; then
  if [ -n "$PERIOD" ]; then
    python pipeline/run.py --source helix --helix-period "$PERIOD"
  else
    # Full current open scope plus the separate successful-closures-yesterday slice.
    python pipeline/run.py --source helix
  fi
else
  python pipeline/run.py --source file
fi

# Fully unattended delivery: this is safe to run after every pipeline refresh.
# The sender checks schedule, freshness, enabled subscriptions and idempotency.
python -m notifications.sender
