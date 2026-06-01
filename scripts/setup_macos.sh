#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-python3.11}"
SOURCE_DATA_DIR="${SOURCE_DATA_DIR:-}"
CONSTRAINTS_FILE="${CONSTRAINTS_FILE:-constraints-macos-arm64.txt}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3.11 is required. Set PYTHON_BIN=/path/to/python3.11 if needed." >&2
  exit 1
fi

if [[ ! -d .venv ]]; then
  "$PYTHON_BIN" -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
if [[ -f "$CONSTRAINTS_FILE" ]]; then
  .venv/bin/python -m pip install -r requirements.txt -c "$CONSTRAINTS_FILE"
else
  .venv/bin/python -m pip install -r requirements.txt
fi

mkdir -p runtime chroma_db .cache

if [[ ! -e .env ]]; then
  cp .env.example .env
fi

if [[ -n "$SOURCE_DATA_DIR" ]]; then
  if [[ ! -d "$SOURCE_DATA_DIR" ]]; then
    echo "SOURCE_DATA_DIR does not exist: $SOURCE_DATA_DIR" >&2
    exit 1
  fi
  if [[ -e data && ! -L data ]]; then
    echo "data exists and is not a symlink; leaving it unchanged." >&2
  elif [[ ! -e data ]]; then
    ln -s "$SOURCE_DATA_DIR" data
  fi
fi

echo "macOS setup complete."
echo "Run scripts/doctor.sh to verify local readiness."
