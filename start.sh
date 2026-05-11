#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

KEY="${VISION_MCP_KEYCHAIN_SERVICE:-dashscope-api-key}"
if [[ -z "${DASHSCOPE_API_KEY:-}" ]]; then
  export DASHSCOPE_API_KEY
  # macOS Keychain generic password (-s service name).
  # If this fails empty, callers may still rely on ~/.env loaded by dotenv in Python.
  DASHSCOPE_API_KEY="$(security find-generic-password -s "$KEY" -w 2>/dev/null || true)"
fi

# Prefer repo venv interpreter if present
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  exec "$ROOT/.venv/bin/python" -m vision_mcp "$@"
fi

exec python3 -m vision_mcp "$@"
