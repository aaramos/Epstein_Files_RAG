from __future__ import annotations

import argparse
import json
import os
import subprocess
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


def scan_indexer_processes() -> tuple[list[dict], bool]:
    pgrep_processes, pgrep_available = processes_from_pgrep()
    if pgrep_processes or not pgrep_available:
        return pgrep_processes, pgrep_available
    return processes_from_ps()


def processes_from_pgrep() -> tuple[list[dict], bool]:
    try:
        result = subprocess.run(
            ["pgrep", "-fl", "ingest.py"],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return [], False
    unavailable = "Cannot get process list" in result.stderr or "service not found" in result.stderr
    if unavailable:
        return [], False
    return parse_process_lines(result.stdout.splitlines()), True


def processes_from_ps() -> tuple[list[dict], bool]:
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return [], False
    unavailable = "Cannot get process list" in result.stderr or "service not found" in result.stderr
    if unavailable:
        return [], False
    return parse_process_lines(line for line in result.stdout.splitlines() if "ingest.py" in line), True


def parse_process_lines(lines) -> list[dict]:
    processes = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        pid, _, command = stripped.partition(" ")
        if not pid.isdigit():
            continue
        processes.append({"pid": int(pid), "command": command.strip()})
    return processes


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
    processes, process_scan_available = scan_indexer_processes()
    process_missing = bool(status.indexing_active and process_scan_available and not processes)
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
        "indexer_process_count": len(processes),
        "indexer_processes": processes,
        "indexer_process_missing": process_missing,
        "indexer_process_scan_available": process_scan_available,
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
    if not payload["indexer_process_scan_available"]:
        print("Indexer processes: unavailable")
    elif payload["indexer_process_count"]:
        process_summary = ", ".join(str(process["pid"]) for process in payload["indexer_processes"])
        print(f"Indexer processes: {process_summary}")
    else:
        print("Indexer processes: none")
    if payload["indexer_process_missing"]:
        print("Warning: manifest shows active indexing but no ingest.py process was found")
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
