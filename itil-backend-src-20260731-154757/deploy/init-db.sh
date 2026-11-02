#!/usr/bin/env bash
set -euo pipefail

cd /app

python -m app_core.migrations

dbt run --profiles-dir dbt --project-dir dbt

echo "Database schema and dbt models are ready."
