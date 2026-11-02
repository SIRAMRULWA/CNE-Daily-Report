#!/usr/bin/env bash
set -euo pipefail

cd /app

# Safe on every start: already-applied migrations are checksum-verified no-ops.
python -m app_core.migrations

exec uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers "${API_WORKERS:-1}"
