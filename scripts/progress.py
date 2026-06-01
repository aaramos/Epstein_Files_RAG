from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from datetime import timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
SAMPLE_LIMIT = 5

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from index_state import default_data_dir, default_manifest_path, load_manifest, read_index_status
from index_lock import process_alive, read_lock


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report local download and Chroma index progress.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--fail-stale", action="store_true", help="Exit non-zero when active indexing appears stalled or orphaned.")
    parser.add_argument("--watch", type=float, metavar="SECONDS", help="Refresh progress every N seconds until interrupted or complete.")
    parser.add_argument("--watch-count", type=int, metavar="N", help="Stop watch mode after N refreshes.")
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


def human_size(num_bytes: int | None) -> str:
    if num_bytes is None:
        return "unknown"
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"


def data_payload(root: Path = ROOT) -> dict:
    data_dir = default_data_dir(root)
    try:
        resolved = data_dir.resolve(strict=False)
    except OSError:
        resolved = data_dir
    parquet_files = list(data_dir.glob("epstein_files-*.parquet"))
    total_bytes = 0
    size_known = True
    for path in parquet_files:
        try:
            total_bytes += path.stat().st_size
        except OSError:
            size_known = False
    return {
        "path": str(data_dir),
        "resolved_path": str(resolved),
        "is_symlink": data_dir.is_symlink(),
        "size_bytes": total_bytes if size_known else None,
        "size_human": human_size(total_bytes if size_known else None),
    }


def directory_size_bytes(path: Path) -> int | None:
    total_bytes = 0
    try:
        iterator = path.rglob("*")
        for item in iterator:
            try:
                if item.is_file():
                    total_bytes += item.stat().st_size
            except OSError:
                return None
    except OSError:
        return None
    return total_bytes


def index_storage_payload(root: Path = ROOT) -> dict:
    db_dir = Path(os.getenv("DB_PATH", str(root / "chroma_db")))
    size_bytes = directory_size_bytes(db_dir) if db_dir.exists() else None
    disk_target = db_dir if db_dir.exists() else db_dir.parent
    try:
        usage = shutil.disk_usage(disk_target)
        free_bytes = usage.free
        total_bytes = usage.total
    except OSError:
        free_bytes = None
        total_bytes = None
    return {
        "path": str(db_dir),
        "size_bytes": size_bytes,
        "size_human": human_size(size_bytes),
        "free_bytes": free_bytes,
        "free_human": human_size(free_bytes),
        "total_bytes": total_bytes,
        "total_human": human_size(total_bytes),
    }


def index_log_path(root: Path = ROOT) -> Path:
    return Path(os.getenv("INDEX_LOG_PATH", str(root / "runtime" / "index_full.log")))


def index_lock_path(root: Path = ROOT) -> Path:
    return Path(os.getenv("INDEX_LOCK_PATH", str(root / "runtime" / "index_full.lock")))


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


def lock_payload(now: datetime) -> dict:
    path = index_lock_path(ROOT)
    payload = read_lock(path)
    if not isinstance(payload, dict):
        return {
            "path": str(path),
            "present": False,
            "pid": None,
            "command": None,
            "created_at": None,
            "age_seconds": None,
            "pid_alive": False,
            "stale": False,
        }

    pid = payload.get("pid")
    created_at = parse_time(payload.get("created_at"))
    age = (now - created_at).total_seconds() if created_at else None
    pid_alive = process_alive(pid) if isinstance(pid, int) else False
    return {
        "path": str(path),
        "present": True,
        "pid": pid if isinstance(pid, int) else None,
        "command": payload.get("command"),
        "created_at": payload.get("created_at"),
        "age_seconds": age,
        "pid_alive": pid_alive,
        "stale": not pid_alive,
    }


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
    eta_at = now + timedelta(seconds=eta) if eta is not None else None
    eta_at_local = eta_at.astimezone() if eta_at else None
    manifest_age = file_age_seconds(default_manifest_path(ROOT), now)
    stale_after = stale_seconds()
    log_age = file_age_seconds(index_log_path(ROOT), now)
    processes, process_scan_available = scan_indexer_processes()
    process_missing = bool(status.indexing_active and process_scan_available and not processes)
    stale = bool(status.indexing_active and log_age is not None and log_age > stale_after)
    lock = lock_payload(now)
    data = data_payload(ROOT)
    index_storage = index_storage_payload(ROOT)
    indexed_fraction = status.indexed_files / status.expected_files if status.expected_files else None
    projected_index_size = None
    if index_storage["size_bytes"] is not None and indexed_fraction and indexed_fraction > 0:
        projected_index_size = int(index_storage["size_bytes"] / indexed_fraction)

    return {
        "data": data,
        "index_storage": index_storage,
        "downloaded_files": status.downloaded_files,
        "expected_files": status.expected_files,
        "indexed_files": status.indexed_files,
        "indexed_fraction": indexed_fraction,
        "projected_index_size_bytes": projected_index_size,
        "projected_index_size_human": human_size(projected_index_size),
        "in_progress_files": status.in_progress_files,
        "in_progress_names": list(status.in_progress_names),
        "indexed_documents": status.indexed_docs,
        "indexed_chunks": status.indexed_chunks,
        "missing_indexed_files": len(status.missing_indexed_names),
        "missing_indexed_sample": list(status.missing_indexed_names[:SAMPLE_LIMIT]),
        "unexpected_indexed_files": len(status.unexpected_indexed_names),
        "unexpected_indexed_sample": list(status.unexpected_indexed_names[:SAMPLE_LIMIT]),
        "indexing_active": status.indexing_active,
        "complete": status.complete,
        "elapsed_seconds": elapsed,
        "rate_files_per_minute": rate * 60 if rate else None,
        "eta_seconds": eta,
        "eta_at_utc": eta_at.isoformat() if eta_at else None,
        "eta_at_local": eta_at_local.isoformat() if eta_at_local else None,
        "manifest_age_seconds": manifest_age,
        "index_log_age_seconds": log_age,
        "stale_seconds": stale_after,
        "stale": stale,
        "indexer_process_count": len(processes),
        "indexer_processes": processes,
        "indexer_process_missing": process_missing,
        "indexer_process_scan_available": process_scan_available,
        "index_lock": lock,
    }


def print_human(payload: dict) -> None:
    data = payload.get("data") or {}
    if data:
        print(f"Data path: {data.get('path')}")
        resolved = data.get("resolved_path")
        if resolved and resolved != data.get("path"):
            print(f"Data resolves to: {resolved}")
        print(f"Data size: {data.get('size_human', 'unknown')}")
    index_storage = payload.get("index_storage") or {}
    if index_storage:
        print(f"Index path: {index_storage.get('path')}")
        print(f"Index size: {index_storage.get('size_human', 'unknown')}")
        print(f"Index volume free: {index_storage.get('free_human', 'unknown')} of {index_storage.get('total_human', 'unknown')}")
    if payload.get("projected_index_size_human") != "unknown":
        print(f"Projected final index size: {payload['projected_index_size_human']}")
    print(f"Downloaded files: {payload['downloaded_files']}/{payload['expected_files']}")
    indexed_fraction = payload["indexed_fraction"] or 0
    print(f"Indexed files: {payload['indexed_files']}/{payload['expected_files']} ({indexed_fraction:.1%})")
    print(f"In progress: {', '.join(payload['in_progress_names']) if payload['in_progress_names'] else 'none'}")
    print(f"Indexed documents: {payload['indexed_documents']:,}")
    print(f"Indexed chunks: {payload['indexed_chunks']:,}")
    if payload["missing_indexed_files"]:
        print(f"Downloaded files not indexed: {payload['missing_indexed_files']}")
    if payload["unexpected_indexed_files"]:
        print(f"Manifest entries missing from data: {payload['unexpected_indexed_files']}")
    print(f"Elapsed: {human_duration(payload['elapsed_seconds'])}")
    rate = payload["rate_files_per_minute"]
    print(f"Rate: {rate:.2f} files/min" if rate else "Rate: unknown")
    print(f"ETA: {human_duration(payload['eta_seconds'])}")
    if payload.get("eta_at_utc"):
        print(f"Estimated completion UTC: {payload['eta_at_utc']}")
    if payload.get("eta_at_local"):
        print(f"Estimated completion local: {payload['eta_at_local']}")
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
    lock = payload["index_lock"]
    if lock["present"]:
        alive = "alive" if lock["pid_alive"] else "not alive"
        print(f"Index lock: PID {lock['pid']} ({alive}), age {human_duration(lock['age_seconds'])}")
    else:
        print("Index lock: none")
    if payload["indexing_active"] and not lock["present"]:
        print("Warning: manifest shows active indexing but no index lock was found")
    if lock["stale"]:
        print("Warning: index lock PID is not running")
    if payload["stale"]:
        print(f"Warning: index log has been quiet for more than {human_duration(payload['stale_seconds'])}")


def stale_failure_reason(payload: dict) -> str | None:
    if payload["stale"]:
        return f"index log has been quiet for more than {human_duration(payload['stale_seconds'])}"
    if payload["indexer_process_missing"]:
        return "manifest shows active indexing but no ingest.py process was found"
    lock = payload["index_lock"]
    if payload["indexing_active"] and not lock["present"]:
        return "manifest shows active indexing but no index lock was found"
    if lock["stale"]:
        return "index lock PID is not running"
    return None


def main() -> None:
    args = parse_args()
    if args.watch is not None and args.json:
        raise SystemExit("--watch cannot be combined with --json")
    if args.watch is not None and args.watch <= 0:
        raise SystemExit("--watch must be greater than 0")
    if args.watch_count is not None and args.watch_count <= 0:
        raise SystemExit("--watch-count must be greater than 0")
    if args.watch_count is not None and args.watch is None:
        raise SystemExit("--watch-count requires --watch")

    iterations = 0
    while True:
        payload = progress_payload()
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            if args.watch is not None and iterations:
                print()
            print_human(payload)
        if args.fail_stale:
            reason = stale_failure_reason(payload)
            if reason:
                raise SystemExit(f"Index progress is stale: {reason}")
        iterations += 1
        if args.watch is None or payload["complete"]:
            break
        if args.watch_count is not None and iterations >= args.watch_count:
            break
        time.sleep(args.watch)


if __name__ == "__main__":
    main()
