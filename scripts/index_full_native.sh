#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export EMBEDDING_DEVICE="${EMBEDDING_DEVICE:-auto}"
export INGEST_BATCH_SIZE="${INGEST_BATCH_SIZE:-512}"
export PARQUET_ROW_BATCH_SIZE="${PARQUET_ROW_BATCH_SIZE:-2048}"
LOCK_PATH="${INDEX_LOCK_PATH:-runtime/index_full.lock}"
OWNER_PID="$$"

mkdir -p runtime
.venv/bin/python scripts/index_lock.py acquire "$LOCK_PATH" \
  --pid "$OWNER_PID" \
  --command "$0 $*"
trap '.venv/bin/python scripts/index_lock.py release "$LOCK_PATH" --pid "$OWNER_PID" >/dev/null 2>&1 || true' EXIT

.venv/bin/python ingest.py --all --skip-download \
  --embedding-device "$EMBEDDING_DEVICE" \
  --batch-size "$INGEST_BATCH_SIZE" \
  --row-batch-size "$PARQUET_ROW_BATCH_SIZE"
