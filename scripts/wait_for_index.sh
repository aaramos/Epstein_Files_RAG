#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

INTERVAL_SECONDS="${INTERVAL_SECONDS:-60}"
RUN_FINAL_VALIDATE="${RUN_FINAL_VALIDATE:-1}"

while true; do
  .venv/bin/python scripts/progress.py

  if .venv/bin/python - <<'PY'
import json
import os
from pathlib import Path

expected = int(os.getenv("TOTAL_PARQUET_FILES", os.getenv("EXPECTED_PARQUET_FILES", "634")))
manifest_path = Path(os.getenv("INGEST_MANIFEST_PATH", "chroma_db/ingest_manifest.json"))
try:
    manifest = json.loads(manifest_path.read_text())
except (OSError, json.JSONDecodeError):
    raise SystemExit(1)

completed = manifest.get("completed_files", {})
in_progress = manifest.get("in_progress", {})
raise SystemExit(0 if len(completed) >= expected and not in_progress else 1)
PY
  then
    echo "Full index is complete."
    if [[ "$RUN_FINAL_VALIDATE" == "1" ]]; then
      scripts/validate_rag.sh --require-full-index --rag
    fi
    exit 0
  fi

  echo "Waiting ${INTERVAL_SECONDS}s before next index check..."
  sleep "$INTERVAL_SECONDS"
done
