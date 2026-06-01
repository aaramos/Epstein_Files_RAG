#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="${DIAGNOSTICS_DIR:-runtime/diagnostics/${STAMP}}"
LATEST_LINK="${DIAGNOSTICS_LATEST_LINK:-runtime/diagnostics/latest}"

mkdir -p "$OUT_DIR"

run_capture() {
  local name="$1"
  shift
  {
    echo "# $*"
    echo
    "$@"
  } >"${OUT_DIR}/${name}.txt" 2>&1 || true
}

run_raw_capture() {
  local name="$1"
  shift
  "$@" >"${OUT_DIR}/${name}.json" 2>"${OUT_DIR}/${name}.err.txt" || true
}

run_capture progress scripts/progress.sh
run_raw_capture progress scripts/progress.sh --json
run_capture doctor scripts/doctor.sh
FINAL_AUDIT_MODE="partial_skip_app"
if .venv/bin/python - <<'PY'
from index_state import read_index_status

raise SystemExit(0 if read_index_status().complete else 1)
PY
then
  FINAL_AUDIT_MODE="full"
  run_capture final_audit scripts/final_audit.sh
  run_raw_capture final_audit scripts/final_audit.sh --json
  run_capture benchmark scripts/benchmark.sh
  run_raw_capture benchmark scripts/benchmark.sh --json
else
  run_capture final_audit scripts/final_audit.sh --allow-incomplete --skip-app
  run_raw_capture final_audit scripts/final_audit.sh --allow-incomplete --skip-app --json
fi
run_capture launchd_status scripts/launchd_manage.sh status
run_capture launchd_validate scripts/launchd_manage.sh validate

if [[ -f runtime/index_full.log ]]; then
  tail -200 runtime/index_full.log >"${OUT_DIR}/index_full.tail.log"
fi

if [[ -f runtime/index_full.err.log ]]; then
  tail -200 runtime/index_full.err.log >"${OUT_DIR}/index_full.err.tail.log"
fi

git status --short >"${OUT_DIR}/git_status.txt"
git log --oneline -20 >"${OUT_DIR}/git_log.txt"

.venv/bin/python - <<'PY' "$OUT_DIR" "$STAMP" "$FINAL_AUDIT_MODE" >"${OUT_DIR}/manifest.json"
import json
import subprocess
import sys
from pathlib import Path

out_dir = Path(sys.argv[1])
stamp = sys.argv[2]
final_audit_mode = sys.argv[3]

def git_value(*args):
    try:
        return subprocess.check_output(["git", *args], text=True).strip()
    except Exception:
        return None

def json_file(name):
    path = out_dir / name
    try:
        return json.loads(path.read_text())
    except Exception:
        return None

progress = json_file("progress.json") or {}
final_audit = json_file("final_audit.json") or {}
data = progress.get("data") or {}
index_storage = progress.get("index_storage") or {}

files = sorted(path.name for path in out_dir.iterdir() if path.is_file() and path.name != "manifest.json")
payload = {
    "generated_at_utc": stamp,
    "git_commit": git_value("rev-parse", "HEAD"),
    "git_branch": git_value("branch", "--show-current"),
    "final_audit_mode": final_audit_mode,
    "summary": {
        "index_complete": progress.get("complete"),
        "indexed_files": progress.get("indexed_files"),
        "expected_files": progress.get("expected_files"),
        "indexed_fraction": progress.get("indexed_fraction"),
        "data_path": data.get("path"),
        "data_resolved_path": data.get("resolved_path"),
        "data_size_human": data.get("size_human"),
        "index_path": index_storage.get("path"),
        "index_size_human": index_storage.get("size_human"),
        "index_free_human": index_storage.get("free_human"),
        "projected_index_size_human": progress.get("projected_index_size_human"),
        "eta_at_local": progress.get("eta_at_local"),
        "eta_at_utc": progress.get("eta_at_utc"),
        "final_audit_complete": final_audit.get("complete"),
        "skipped_gates": final_audit.get("skipped_gates"),
    },
    "files": files,
    "notes": [
        "progress.json contains machine-readable index progress",
        "final_audit.txt contains current completion gate state",
        "final_audit.json contains machine-readable completion gates",
        "benchmark.json contains retrieval timing after full index completion when available",
        "index_full.tail.log contains the latest indexer log lines when available",
    ],
}
print(json.dumps(payload, indent=2, sort_keys=True))
PY

if [[ -z "${DIAGNOSTICS_DIR:-}" ]]; then
  ln -sfn "$(basename "$OUT_DIR")" "$LATEST_LINK"
fi

echo "Diagnostics written to ${OUT_DIR}"
if [[ -z "${DIAGNOSTICS_DIR:-}" ]]; then
  echo "Latest diagnostics link: ${LATEST_LINK}"
fi
