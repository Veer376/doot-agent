#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AEGRA_ROOT="${AEGRA_ROOT:-/Users/aryaveer/Projects/aegra}"
VENV="$AEGRA_ROOT/.venv"
DB_NAME="${AEGRA_POSTGRES_DB:-aegra_doot}"
DB_USER="${AEGRA_POSTGRES_USER:-$(whoami)}"
AEGRA_PORT="${AEGRA_PORT:-2026}"

command -v brew >/dev/null || { echo "Homebrew is required" >&2; exit 1; }
command -v uv >/dev/null || { echo "uv is required" >&2; exit 1; }

brew services start postgresql@18 >/dev/null
brew services start redis >/dev/null

for _ in {1..20}; do
  pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1 && break
  sleep 0.25
done
pg_isready -h 127.0.0.1 -p 5432 >/dev/null
redis-cli -h 127.0.0.1 -p 6379 ping >/dev/null

if ! psql -d postgres -Atqc "select 1 from pg_database where datname='${DB_NAME}'" | grep -q 1; then
  createdb "$DB_NAME"
fi

[[ -x "$VENV/bin/aegra" ]] || {
  echo "Aegra is not installed at $VENV. Set up /Users/aryaveer/Projects/aegra/.venv first." >&2
  exit 1
}

export DATABASE_URL="${DATABASE_URL:-postgresql://${DB_USER}@127.0.0.1:5432/${DB_NAME}}"
export REDIS_BROKER_ENABLED="${REDIS_BROKER_ENABLED:-true}"
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/1}"
export WORKER_COUNT="${WORKER_COUNT:-1}"
export N_JOBS_PER_WORKER="${N_JOBS_PER_WORKER:-1}"
export AUTH_TYPE="${AUTH_TYPE:-noop}"
export ENV_MODE="${ENV_MODE:-LOCAL}"
export ANTIGRAVITY_BASE_URL="${ANTIGRAVITY_BASE_URL:-http://127.0.0.1:8877}"
export ANTIGRAVITY_MODEL="${ANTIGRAVITY_MODEL:-gemini-3.8-flash-low}"
export DOOT_WORKSPACE_ROOT="${DOOT_WORKSPACE_ROOT:-$ROOT}"

cd "$AEGRA_ROOT"
exec "$VENV/bin/aegra" serve \
  -c "$ROOT/aegra.local.json" \
  --host 127.0.0.1 \
  --port "$AEGRA_PORT"
