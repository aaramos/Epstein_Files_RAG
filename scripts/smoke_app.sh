#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

HOST="${STREAMLIT_ADDRESS:-127.0.0.1}"
if [[ -n "${STREAMLIT_PORT:-}" ]]; then
  PORT="$STREAMLIT_PORT"
  if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port ${PORT} is already in use; set STREAMLIT_PORT to an unused port." >&2
    exit 1
  fi
else
  PORT="$(
    .venv/bin/python - <<'PY'
import socket

with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
  )"
fi
URL="http://${HOST}:${PORT}/"
OUT_LOG="${APP_SMOKE_OUT_LOG:-runtime/app_smoke.out.log}"
ERR_LOG="${APP_SMOKE_ERR_LOG:-runtime/app_smoke.err.log}"

mkdir -p runtime

STREAMLIT_PORT="$PORT" STREAMLIT_ADDRESS="$HOST" scripts/run_native.sh >"$OUT_LOG" 2>"$ERR_LOG" &
APP_PID="$!"

cleanup() {
  if kill -0 "$APP_PID" >/dev/null 2>&1; then
    kill "$APP_PID" >/dev/null 2>&1 || true
    wait "$APP_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

for _ in $(seq 1 30); do
  if curl -fsS "$URL" >/dev/null 2>&1; then
    echo "Streamlit app smoke OK at ${URL}"
    exit 0
  fi
  if ! kill -0 "$APP_PID" >/dev/null 2>&1; then
    echo "Streamlit app exited before becoming ready." >&2
    tail -40 "$ERR_LOG" >&2 || true
    exit 1
  fi
  sleep 1
done

echo "Timed out waiting for Streamlit app at ${URL}" >&2
tail -40 "$ERR_LOG" >&2 || true
exit 1
