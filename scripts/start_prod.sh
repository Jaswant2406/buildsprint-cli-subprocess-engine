#!/usr/bin/env bash
# Single-command production runner for Linux / macOS
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "==> Preparing BuildSprint Production Deployment..."

# 1. Frontend Build
cd "${ROOT_DIR}/frontend"
if [ ! -d "node_modules" ]; then
    echo "==> Installing frontend dependencies..."
    npm install
fi
echo "==> Building frontend assets for single-origin distribution..."
npm run build

# 2. Python Environment & Server
cd "${ROOT_DIR}"
PY="python"
if [ -f "${ROOT_DIR}/.venv/bin/python" ]; then
    PY="${ROOT_DIR}/.venv/bin/python"
elif command -v python3 &>/dev/null; then
    PY="python3"
fi

export APP_ENV="${APP_ENV:-production}"
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8000}"

echo "==> Starting single-origin server on http://${HOST}:${PORT} [APP_ENV=${APP_ENV}]..."

exec "$PY" -m uvicorn app.main:app --app-dir backend --host "$HOST" --port "$PORT"
