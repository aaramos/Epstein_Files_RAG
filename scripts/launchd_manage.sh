#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

ACTION="${1:-status}"
ROOT_DIR="$(pwd)"
LAUNCHD_DIR="${HOME}/Library/LaunchAgents"
GUI_DOMAIN="gui/$(id -u)"

services=(
  "com.epstein-rag.app"
  "com.epstein-rag.indexer"
)

usage() {
  echo "Usage: scripts/launchd_manage.sh {install|uninstall|status|start|stop} [app|indexer|all]" >&2
}

selected_services() {
  local target="${1:-all}"
  case "$target" in
    app) echo "com.epstein-rag.app" ;;
    indexer) echo "com.epstein-rag.indexer" ;;
    all) printf '%s\n' "${services[@]}" ;;
    *) usage; exit 2 ;;
  esac
}

plist_path() {
  echo "${LAUNCHD_DIR}/${1}.plist"
}

render_plist() {
  local label="$1"
  local source="launchd/${label}.plist.example"
  local destination
  destination="$(plist_path "$label")"

  mkdir -p "$LAUNCHD_DIR" runtime
  sed "s#/Users/macstudio/Documents/RAG/Epstein_Files_RAG_macstudio#${ROOT_DIR}#g" \
    "$source" > "$destination"
  plutil -lint "$destination" >/dev/null
  echo "Installed ${destination}"
}

bootstrap_service() {
  local label="$1"
  launchctl bootout "$GUI_DOMAIN" "$(plist_path "$label")" >/dev/null 2>&1 || true
  launchctl bootstrap "$GUI_DOMAIN" "$(plist_path "$label")"
  echo "Loaded ${label}"
}

uninstall_service() {
  local label="$1"
  launchctl bootout "$GUI_DOMAIN" "$(plist_path "$label")" >/dev/null 2>&1 || true
  rm -f "$(plist_path "$label")"
  echo "Removed ${label}"
}

service_status() {
  local label="$1"
  if launchctl print "${GUI_DOMAIN}/${label}" >/dev/null 2>&1; then
    echo "${label}: loaded"
  else
    echo "${label}: not loaded"
  fi
}

start_service() {
  local label="$1"
  launchctl kickstart -k "${GUI_DOMAIN}/${label}"
  echo "Started ${label}"
}

stop_service() {
  local label="$1"
  launchctl kill TERM "${GUI_DOMAIN}/${label}" >/dev/null 2>&1 || true
  echo "Stopped ${label}"
}

TARGET="${2:-all}"

case "$ACTION" in
  install)
    for service in $(selected_services "$TARGET"); do
      render_plist "$service"
      bootstrap_service "$service"
    done
    ;;
  uninstall)
    for service in $(selected_services "$TARGET"); do
      uninstall_service "$service"
    done
    ;;
  status)
    for service in $(selected_services "$TARGET"); do
      service_status "$service"
    done
    ;;
  start)
    for service in $(selected_services "$TARGET"); do
      start_service "$service"
    done
    ;;
  stop)
    for service in $(selected_services "$TARGET"); do
      stop_service "$service"
    done
    ;;
  *)
    usage
    exit 2
    ;;
esac
