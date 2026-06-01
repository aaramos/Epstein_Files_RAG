#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

INTERVAL_SECONDS="${INTERVAL_SECONDS:-60}"
RUN_FINAL_AUDIT="${RUN_FINAL_AUDIT:-1}"
RUN_FINAL_VALIDATE="${RUN_FINAL_VALIDATE:-1}"
RUN_COMPLETION_DIAGNOSTICS="${RUN_COMPLETION_DIAGNOSTICS:-1}"

while true; do
  set +e
  .venv/bin/python scripts/progress.py --fail-stale
  PROGRESS_STATUS="$?"
  set -e
  if [[ "$PROGRESS_STATUS" != "0" ]]; then
    if [[ "$RUN_COMPLETION_DIAGNOSTICS" == "1" ]]; then
      scripts/collect_diagnostics.sh
    fi
    exit "$PROGRESS_STATUS"
  fi

  if .venv/bin/python - <<'PY'
from index_state import read_index_status

raise SystemExit(0 if read_index_status().complete else 1)
PY
  then
    echo "Full index is complete."
    .venv/bin/python scripts/index_lock.py release-stale "${INDEX_LOCK_PATH:-runtime/index_full.lock}"
    VALIDATION_STATUS=0
    if [[ "$RUN_FINAL_AUDIT" == "1" ]]; then
      scripts/final_audit.sh || VALIDATION_STATUS="$?"
    elif [[ "$RUN_FINAL_VALIDATE" == "1" ]]; then
      scripts/validate_rag.sh --require-full-index --rag || VALIDATION_STATUS="$?"
    fi
    if [[ "$RUN_COMPLETION_DIAGNOSTICS" == "1" ]]; then
      scripts/collect_diagnostics.sh
    fi
    exit "$VALIDATION_STATUS"
  fi

  echo "Waiting ${INTERVAL_SECONDS}s before next index check..."
  sleep "$INTERVAL_SECONDS"
done
