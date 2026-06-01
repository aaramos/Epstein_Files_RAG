#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

FAISS_INDEX_DIR="${FAISS_INDEX_DIR:-./faiss_index}"

.venv/bin/python scripts/validate_faiss.py --path "$FAISS_INDEX_DIR"
RETRIEVER_BACKEND=auto FAISS_INDEX_DIR="$FAISS_INDEX_DIR" \
  .venv/bin/python scripts/retrieval_backend_status.py --expect faiss_hnsw

cat <<EOF
FAISS is validated and ready.

To run the app on FAISS explicitly:
  RETRIEVER_BACKEND=faiss FAISS_INDEX_DIR="$FAISS_INDEX_DIR" scripts/run_native.sh

With RETRIEVER_BACKEND=auto, the app will also prefer FAISS once this completed
index is present.
EOF
