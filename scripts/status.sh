#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

exec .venv/bin/python ingest.py --status --check-hub
