#!/bin/zsh
set -euo pipefail

script_dir="${0:A:h}"
repo_dir="${script_dir:h}"

export ANKICONNECT_URL="${ANKICONNECT_URL:-http://127.0.0.1:28765}"
export ANKI_REVIEW_WRITEBACK_ENABLED="${ANKI_REVIEW_WRITEBACK_ENABLED:-false}"
export ACTIONS_HOST="${ACTIONS_HOST:-127.0.0.1}"
export ACTIONS_PORT="${ACTIONS_PORT:-28766}"

cd "$repo_dir"
exec python3 actions_api.py
