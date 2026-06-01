#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export LLM_PROVIDER="${LLM_PROVIDER:-OMLX}"
export OMLX_BASE_URL="${OMLX_BASE_URL:-http://127.0.0.1:1234/v1}"
export OMLX_MODEL="${OMLX_MODEL:-Gemma4-MTP-26B-BF16}"
export RETRIEVER_BACKEND="${RETRIEVER_BACKEND:-auto}"
export FAISS_INDEX_DIR="${FAISS_INDEX_DIR:-./faiss_index}"

exec .venv/bin/python -m streamlit run app.py \
  --server.address "${STREAMLIT_ADDRESS:-127.0.0.1}" \
  --server.port "${STREAMLIT_PORT:-8501}"
