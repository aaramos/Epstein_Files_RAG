#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export EMBEDDING_DEVICE="${EMBEDDING_DEVICE:-auto}"
export INGEST_BATCH_SIZE="${INGEST_BATCH_SIZE:-512}"
export PARQUET_ROW_BATCH_SIZE="${PARQUET_ROW_BATCH_SIZE:-2048}"
export CHROMA_HNSW_BATCH_SIZE="${CHROMA_HNSW_BATCH_SIZE:-256}"
export CHROMA_HNSW_SYNC_THRESHOLD="${CHROMA_HNSW_SYNC_THRESHOLD:-256}"
LOCK_PATH="${INDEX_LOCK_PATH:-runtime/index_full.lock}"
OWNER_PID="$$"
CHILD_PID=""

terminate_child() {
  if [[ -n "$CHILD_PID" ]] && kill -0 "$CHILD_PID" >/dev/null 2>&1; then
    kill -TERM "$CHILD_PID" >/dev/null 2>&1 || true
  fi
}

cleanup() {
  local status="$?"
  if [[ -n "$CHILD_PID" ]] && kill -0 "$CHILD_PID" >/dev/null 2>&1; then
    terminate_child
    wait "$CHILD_PID" >/dev/null 2>&1 || true
  fi
  .venv/bin/python scripts/index_lock.py release "$LOCK_PATH" --pid "$OWNER_PID" >/dev/null 2>&1 || true
  exit "$status"
}

mkdir -p runtime
.venv/bin/python scripts/index_lock.py acquire "$LOCK_PATH" \
  --pid "$OWNER_PID" \
  --command "$0 $*"
trap terminate_child TERM INT
trap cleanup EXIT

.venv/bin/python ingest.py --all --skip-download \
  --embedding-device "$EMBEDDING_DEVICE" \
  --batch-size "$INGEST_BATCH_SIZE" \
  --row-batch-size "$PARQUET_ROW_BATCH_SIZE" &
CHILD_PID="$!"
wait "$CHILD_PID"
