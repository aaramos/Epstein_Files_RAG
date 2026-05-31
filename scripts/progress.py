from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("DATA_PATH", str(ROOT / "data")))
MANIFEST_PATH = Path(os.getenv("INGEST_MANIFEST_PATH", str(ROOT / "chroma_db" / "ingest_manifest.json")))
TOTAL_FILES = int(os.getenv("TOTAL_PARQUET_FILES", "634"))


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def human_duration(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def load_manifest() -> dict:
    try:
        return json.loads(MANIFEST_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {"completed_files": {}, "in_progress": {}}


def main() -> None:
    manifest = load_manifest()
    completed = manifest.get("completed_files", {})
    in_progress = manifest.get("in_progress", {})
    local_files = len(list(DATA_DIR.glob("epstein_files-*.parquet")))
    completed_times = [
        parse_time(item.get("indexed_at"))
        for item in completed.values()
        if isinstance(item, dict)
    ]
    completed_times = [value for value in completed_times if value is not None]
    started_times = [
        parse_time(item.get("started_at"))
        for item in in_progress.values()
        if isinstance(item, dict)
    ]
    started_times = [value for value in started_times if value is not None]

    now = datetime.now(timezone.utc)
    first_time = min(completed_times + started_times) if (completed_times or started_times) else None
    elapsed = (now - first_time).total_seconds() if first_time else None
    completed_count = len(completed)
    rate = completed_count / elapsed if elapsed and elapsed > 0 else None
    remaining = max(0, TOTAL_FILES - completed_count)
    eta = remaining / rate if rate else None
    documents = sum(item.get("documents", 0) for item in completed.values() if isinstance(item, dict))
    chunks = sum(item.get("chunks", 0) for item in completed.values() if isinstance(item, dict))

    print(f"Downloaded files: {local_files}/{TOTAL_FILES}")
    print(f"Indexed files: {completed_count}/{TOTAL_FILES} ({completed_count / TOTAL_FILES:.1%})")
    print(f"In progress: {', '.join(sorted(in_progress)) if in_progress else 'none'}")
    print(f"Indexed documents: {documents:,}")
    print(f"Indexed chunks: {chunks:,}")
    print(f"Elapsed: {human_duration(elapsed)}")
    print(f"Rate: {rate * 60:.2f} files/min" if rate else "Rate: unknown")
    print(f"ETA: {human_duration(eta)}")


if __name__ == "__main__":
    main()
