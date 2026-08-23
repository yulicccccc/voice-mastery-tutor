#!/bin/zsh
set -euo pipefail

exec cloudflared tunnel \
  --url "${ACTIONS_LOCAL_URL:-http://127.0.0.1:28766}" \
  --no-autoupdate
