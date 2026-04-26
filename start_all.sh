#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
ROOT_ENV_FILE="$ROOT_DIR/.env"

load_root_env() {
  if [[ ! -f "$ROOT_ENV_FILE" ]]; then
    echo "No env file found at $ROOT_ENV_FILE (continuing without it)."
    return
  fi

  echo "Loading environment from $ROOT_ENV_FILE"

  # Export all loaded vars so child processes inherit them.
  set -a
  # shellcheck disable=SC1090
  source "$ROOT_ENV_FILE"
  set +a
}

# Prefer local virtualenv Python if available.
if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_CMD="$ROOT_DIR/.venv/bin/python"
elif [[ -x "$ROOT_DIR/.venv/Scripts/python.exe" ]]; then
  PYTHON_CMD="$ROOT_DIR/.venv/Scripts/python.exe"
else
  PYTHON_CMD="python"
fi

cleanup() {
  echo
  echo "Stopping services..."
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  wait || true
}

trap cleanup INT TERM EXIT

PIDS=()

echo "Using Python: $PYTHON_CMD"
load_root_env

echo "Starting backend API on http://127.0.0.1:8000 ..."
"$PYTHON_CMD" -m uvicorn backend.app.main:app --reload &
PIDS+=("$!")

echo "Starting MCP server on http://127.0.0.1:8010/mcp ..."
"$PYTHON_CMD" -m backend.mcp &
PIDS+=("$!")

echo "Starting frontend on http://127.0.0.1:5173 ..."
if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "Installing frontend dependencies..."
  (cd "$FRONTEND_DIR" && npm install)
fi
(cd "$FRONTEND_DIR" && npm run dev) &
PIDS+=("$!")

echo
echo "All services started. Press Ctrl+C to stop all."
echo

wait