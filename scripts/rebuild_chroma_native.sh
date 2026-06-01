#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

TARGET_DB="${CHROMA_REBUILD_DB_PATH:-./chroma_db_rebuild}"
OVERWRITE="${CHROMA_REBUILD_OVERWRITE:-0}"

if [[ "$TARGET_DB" == "chroma_db" || "$TARGET_DB" == "./chroma_db" ]]; then
  echo "Refusing to rebuild directly over the live chroma_db. Use a separate CHROMA_REBUILD_DB_PATH."
  exit 2
fi

if [[ -e "$TARGET_DB" ]] && [[ -n "$(find "$TARGET_DB" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
  if [[ "$OVERWRITE" != "1" ]]; then
    echo "$TARGET_DB already exists and is not empty. Set CHROMA_REBUILD_OVERWRITE=1 to replace it."
    exit 2
  fi
  rm -rf "$TARGET_DB"
fi

mkdir -p "$TARGET_DB" runtime

export DB_PATH="$TARGET_DB"
export INGEST_MANIFEST_PATH="$TARGET_DB/ingest_manifest.json"
export EMBEDDING_DEVICE="${EMBEDDING_DEVICE:-auto}"
export INGEST_BATCH_SIZE="${INGEST_BATCH_SIZE:-512}"
export PARQUET_ROW_BATCH_SIZE="${PARQUET_ROW_BATCH_SIZE:-2048}"
export CHROMA_HNSW_BATCH_SIZE="${CHROMA_HNSW_BATCH_SIZE:-256}"
export CHROMA_HNSW_SYNC_THRESHOLD="${CHROMA_HNSW_SYNC_THRESHOLD:-256}"

if [[ -n "${CHROMA_REBUILD_LIMIT:-}" ]]; then
  .venv/bin/python ingest.py \
    --num-files "$CHROMA_REBUILD_LIMIT" \
    --skip-download \
    --embedding-device "$EMBEDDING_DEVICE" \
    --batch-size "$INGEST_BATCH_SIZE" \
    --row-batch-size "$PARQUET_ROW_BATCH_SIZE"
else
  .venv/bin/python ingest.py \
    --all \
    --skip-download \
    --embedding-device "$EMBEDDING_DEVICE" \
    --batch-size "$INGEST_BATCH_SIZE" \
    --row-batch-size "$PARQUET_ROW_BATCH_SIZE"
fi

.venv/bin/python scripts/chroma_vector_diagnostics.py --path "$TARGET_DB"
