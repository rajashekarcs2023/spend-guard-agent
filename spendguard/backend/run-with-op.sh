#!/usr/bin/env bash
# Launch SpendGuard with credentials sourced from 1Password at runtime.
# The Stripe key is resolved by `op run` into the process environment; the model
# never sees it. Requires the 1Password CLI (`op`) and a configured op.env.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v op >/dev/null 2>&1; then
  echo "1Password CLI 'op' not found. Install it or use ./run-dev.sh instead." >&2
  exit 1
fi
if [ ! -f op.env ]; then
  echo "op.env not found. Copy op.env.example to op.env and set your references." >&2
  exit 1
fi

exec op run --env-file=op.env -- \
  ./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
