#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v vercel >/dev/null 2>&1; then
  echo "Vercel CLI not found. Install with: npm i -g vercel"
  exit 1
fi

if [[ ! -f .env.local ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env.local
    echo "Created .env.local from .env.example — fill in your keys before generating or publishing."
  else
    echo "Warning: no .env.local found. Create one or run: npm run pull-env"
  fi
fi

if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
elif [[ ! -d .venv ]] && command -v python3 >/dev/null 2>&1; then
  echo "Creating Python virtualenv and installing dependencies…"
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -r requirements.txt -q
fi

echo "Starting Vercel dev server at http://localhost:3000"
vercel dev "$@"
