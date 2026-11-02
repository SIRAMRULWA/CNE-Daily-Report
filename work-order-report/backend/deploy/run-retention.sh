#!/usr/bin/env bash
set -euo pipefail

cd /app
python -m app_core.retention
