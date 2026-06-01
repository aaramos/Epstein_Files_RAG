#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

.venv/bin/python -m compileall app.py ingest.py llm_factory.py rag_chain.py scripts tests
.venv/bin/python -m unittest discover -s tests
scripts/doctor.sh

if .venv/bin/python - <<'PY'
from index_state import read_index_status

raise SystemExit(0 if read_index_status().indexing_active else 1)
PY
then
  echo "Full indexing is active; skipping extra retrieval/benchmark checks to avoid concurrent Chroma read/write pressure."
  echo "Run CHECK_DURING_INDEX=1 scripts/check_all.sh to force them anyway."
  if [[ "${CHECK_DURING_INDEX:-0}" != "1" ]]; then
    exit 0
  fi
fi

scripts/validate_rag.sh --min-docs 3
scripts/benchmark.sh
