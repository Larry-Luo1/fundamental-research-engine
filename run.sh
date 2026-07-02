#!/usr/bin/env bash
# Start the web server. Reads .env for configuration.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "error: .venv missing. Run ./deploy.sh first." >&2
  exit 1
fi
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

exec ./.venv/bin/python -m web
