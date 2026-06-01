from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from index_state import default_manifest_path, load_manifest, read_index_status


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


def main() -> None:
    manifest = load_manifest(default_manifest_path(ROOT))
    status = read_index_status(root=ROOT)
    completed = manifest.get("completed_files", {})
    in_progress = manifest.get("in_progress", {})
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
    rate = status.indexed_files / elapsed if elapsed and elapsed > 0 else None
    remaining = max(0, status.expected_files - status.indexed_files)
    eta = remaining / rate if rate else None

    print(f"Downloaded files: {status.downloaded_files}/{status.expected_files}")
    print(f"Indexed files: {status.indexed_files}/{status.expected_files} ({status.indexed_files / status.expected_files:.1%})")
    print(f"In progress: {', '.join(status.in_progress_names) if status.in_progress_names else 'none'}")
    print(f"Indexed documents: {status.indexed_docs:,}")
    print(f"Indexed chunks: {status.indexed_chunks:,}")
    print(f"Elapsed: {human_duration(elapsed)}")
    print(f"Rate: {rate * 60:.2f} files/min" if rate else "Rate: unknown")
    print(f"ETA: {human_duration(eta)}")


if __name__ == "__main__":
    main()
