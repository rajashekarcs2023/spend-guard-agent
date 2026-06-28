#!/usr/bin/env bash
# Launch SpendGuard for local development (credentials from .env).
# For 1Password-sourced credentials at runtime, use ./run-with-op.sh instead.
set -euo pipefail
cd "$(dirname "$0")"
exec ./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
