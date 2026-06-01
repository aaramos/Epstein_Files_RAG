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
run_capture final_audit scripts/final_audit.sh --allow-incomplete --skip-app
run_raw_capture final_audit scripts/final_audit.sh --allow-incomplete --skip-app --json
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

.venv/bin/python - <<'PY' "$OUT_DIR" "$STAMP" >"${OUT_DIR}/manifest.json"
import json
import subprocess
import sys
from pathlib import Path

out_dir = Path(sys.argv[1])
stamp = sys.argv[2]

def git_value(*args):
    try:
        return subprocess.check_output(["git", *args], text=True).strip()
    except Exception:
        return None

files = sorted(path.name for path in out_dir.iterdir() if path.is_file() and path.name != "manifest.json")
payload = {
    "generated_at_utc": stamp,
    "git_commit": git_value("rev-parse", "HEAD"),
    "git_branch": git_value("branch", "--show-current"),
    "files": files,
    "notes": [
        "progress.json contains machine-readable index progress",
        "final_audit.txt contains current completion gate state",
        "final_audit.json contains machine-readable completion gates",
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
