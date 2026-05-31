#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export EMBEDDING_DEVICE="${EMBEDDING_DEVICE:-auto}"
export INGEST_BATCH_SIZE="${INGEST_BATCH_SIZE:-512}"
export PARQUET_ROW_BATCH_SIZE="${PARQUET_ROW_BATCH_SIZE:-2048}"

exec .venv/bin/python ingest.py --all --skip-download \
  --embedding-device "$EMBEDDING_DEVICE" \
  --batch-size "$INGEST_BATCH_SIZE" \
  --row-batch-size "$PARQUET_ROW_BATCH_SIZE"
