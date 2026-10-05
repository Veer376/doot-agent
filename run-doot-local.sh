#!/usr/bin/env bash
set -euo pipefail

# Doot is allowed to edit this repository while it is running. LangGraph's
# default development hot reload would kill an in-flight run whenever Doot
# writes a watched file, so the canonical local launcher deliberately disables
# reload. Restart this process explicitly when backend code changes.
exec .venv/bin/langgraph dev \
  --config langgraph.local.json \
  --host "${DOOT_LANGGRAPH_HOST:-127.0.0.1}" \
  --port "${DOOT_LANGGRAPH_PORT:-2024}" \
  --no-browser \
  --no-reload \
  "$@"
