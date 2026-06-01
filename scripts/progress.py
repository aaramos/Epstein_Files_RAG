from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from index_state import default_manifest_path, load_manifest, read_index_status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report local download and Chroma index progress.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser.parse_args()


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


def file_age_seconds(path: Path, now: datetime) -> float | None:
    try:
        return now.timestamp() - path.stat().st_mtime
    except OSError:
        return None


def index_log_path(root: Path = ROOT) -> Path:
    return Path(os.getenv("INDEX_LOG_PATH", str(root / "runtime" / "index_full.log")))


def stale_seconds() -> int:
    return int(os.getenv("INDEX_STALE_SECONDS", "600"))


def progress_payload() -> dict:
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
    manifest_age = file_age_seconds(default_manifest_path(ROOT), now)
    stale_after = stale_seconds()
    log_age = file_age_seconds(index_log_path(ROOT), now)
    stale = bool(status.indexing_active and log_age is not None and log_age > stale_after)

    return {
        "downloaded_files": status.downloaded_files,
        "expected_files": status.expected_files,
        "indexed_files": status.indexed_files,
        "indexed_fraction": status.indexed_files / status.expected_files if status.expected_files else None,
        "in_progress_files": status.in_progress_files,
        "in_progress_names": list(status.in_progress_names),
        "indexed_documents": status.indexed_docs,
        "indexed_chunks": status.indexed_chunks,
        "indexing_active": status.indexing_active,
        "complete": status.complete,
        "elapsed_seconds": elapsed,
        "rate_files_per_minute": rate * 60 if rate else None,
        "eta_seconds": eta,
        "manifest_age_seconds": manifest_age,
        "index_log_age_seconds": log_age,
        "stale_seconds": stale_after,
        "stale": stale,
    }


def print_human(payload: dict) -> None:
    print(f"Downloaded files: {payload['downloaded_files']}/{payload['expected_files']}")
    indexed_fraction = payload["indexed_fraction"] or 0
    print(f"Indexed files: {payload['indexed_files']}/{payload['expected_files']} ({indexed_fraction:.1%})")
    print(f"In progress: {', '.join(payload['in_progress_names']) if payload['in_progress_names'] else 'none'}")
    print(f"Indexed documents: {payload['indexed_documents']:,}")
    print(f"Indexed chunks: {payload['indexed_chunks']:,}")
    print(f"Elapsed: {human_duration(payload['elapsed_seconds'])}")
    rate = payload["rate_files_per_minute"]
    print(f"Rate: {rate:.2f} files/min" if rate else "Rate: unknown")
    print(f"ETA: {human_duration(payload['eta_seconds'])}")
    manifest_age = payload["manifest_age_seconds"]
    log_age = payload["index_log_age_seconds"]
    print(f"Manifest updated: {human_duration(manifest_age)} ago" if manifest_age is not None else "Manifest updated: unknown")
    print(f"Index log updated: {human_duration(log_age)} ago" if log_age is not None else "Index log updated: unknown")
    if payload["stale"]:
        print(f"Warning: index log has been quiet for more than {human_duration(payload['stale_seconds'])}")


def main() -> None:
    args = parse_args()
    payload = progress_payload()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print_human(payload)


if __name__ == "__main__":
    main()
