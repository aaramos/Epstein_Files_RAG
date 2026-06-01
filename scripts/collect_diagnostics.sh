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

run_capture progress scripts/progress.sh
run_capture progress_json scripts/progress.sh --json
run_capture doctor scripts/doctor.sh
run_capture final_audit scripts/final_audit.sh --allow-incomplete --skip-app
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

if [[ -z "${DIAGNOSTICS_DIR:-}" ]]; then
  ln -sfn "$(basename "$OUT_DIR")" "$LATEST_LINK"
fi

echo "Diagnostics written to ${OUT_DIR}"
if [[ -z "${DIAGNOSTICS_DIR:-}" ]]; then
  echo "Latest diagnostics link: ${LATEST_LINK}"
fi
