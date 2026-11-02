#!/usr/bin/env bash
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required on the QA server." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required on the QA server." >&2
  exit 1
fi

if [ ! -f .env.qa ]; then
  echo "Missing .env.qa. Copy .env.qa.example to .env.qa and set API_PROXY_URL." >&2
  exit 1
fi

docker compose -f docker-compose.qa.yml up -d --build
docker compose -f docker-compose.qa.yml ps
