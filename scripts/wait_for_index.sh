#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

INTERVAL_SECONDS="${INTERVAL_SECONDS:-60}"
RUN_FINAL_AUDIT="${RUN_FINAL_AUDIT:-1}"
RUN_FINAL_VALIDATE="${RUN_FINAL_VALIDATE:-1}"

while true; do
  .venv/bin/python scripts/progress.py

  if .venv/bin/python - <<'PY'
from index_state import read_index_status

raise SystemExit(0 if read_index_status().complete else 1)
PY
  then
    echo "Full index is complete."
    .venv/bin/python scripts/index_lock.py release-stale "${INDEX_LOCK_PATH:-runtime/index_full.lock}"
    if [[ "$RUN_FINAL_AUDIT" == "1" ]]; then
      scripts/final_audit.sh
    elif [[ "$RUN_FINAL_VALIDATE" == "1" ]]; then
      scripts/validate_rag.sh --require-full-index --rag
    fi
    exit 0
  fi

  echo "Waiting ${INTERVAL_SECONDS}s before next index check..."
  sleep "$INTERVAL_SECONDS"
done
