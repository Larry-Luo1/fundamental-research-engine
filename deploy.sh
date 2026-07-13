#!/usr/bin/env bash
# One-click setup for Linux/macOS. After `git clone`, run: ./deploy.sh
# Then edit .env (password + model settings) and run ./run.sh
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "error: $PY not found. Install Python 3.10+ first." >&2
  exit 1
fi

# The most common Ubuntu gotcha: the venv/ensurepip module is a separate package.
if ! "$PY" -c "import ensurepip" >/dev/null 2>&1; then
  echo "error: Python venv support is missing." >&2
  echo "On Debian/Ubuntu install it first:  sudo apt install python3-venv" >&2
  exit 1
fi

echo "==> creating virtualenv (.venv)"
"$PY" -m venv .venv

echo "==> installing engine + web extra"
./.venv/bin/python -m pip install --quiet --upgrade pip
./.venv/bin/python -m pip install --quiet -e ".[web]"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "==> created .env from template"
fi

echo ""
echo "Setup complete."
if grep -q "change-me" .env; then
  echo "NEXT: edit .env — set FRE_WEB_PASSWORD and model settings — then run ./run.sh"
else
  echo "NEXT: ./run.sh"
fi
