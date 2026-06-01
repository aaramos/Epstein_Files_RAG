#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

SOURCE_DB="${CHROMA_REBUILD_DB_PATH:-./chroma_db_rebuild}"
LIVE_DB="${DB_PATH:-./chroma_db}"

if [[ "$SOURCE_DB" == "$LIVE_DB" ]]; then
  echo "Source and live Chroma paths are the same; refusing to promote."
  exit 2
fi

if [[ ! -d "$SOURCE_DB" ]]; then
  echo "Missing rebuilt Chroma directory: $SOURCE_DB"
  exit 2
fi

if [[ ! -f "$SOURCE_DB/chroma.sqlite3" ]]; then
  echo "Missing rebuilt Chroma SQLite database: $SOURCE_DB/chroma.sqlite3"
  exit 2
fi

.venv/bin/python scripts/validate_chroma.py --path "$SOURCE_DB"

if [[ -e "$LIVE_DB" ]]; then
  BACKUP_DB="${LIVE_DB}.backup.$(date -u +%Y%m%dT%H%M%SZ)"
  mv "$LIVE_DB" "$BACKUP_DB"
  echo "Backed up existing Chroma directory to $BACKUP_DB"
fi

mv "$SOURCE_DB" "$LIVE_DB"
.venv/bin/python scripts/validate_chroma.py --path "$LIVE_DB"

echo "Promoted rebuilt Chroma index to $LIVE_DB"
