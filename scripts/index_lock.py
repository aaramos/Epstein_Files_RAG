from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_lock(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def write_lock(path: Path, pid: int, command: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": pid,
        "command": command,
        "created_at": utc_now(),
    }
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def acquire_lock(path: Path, pid: int, command: str) -> None:
    try:
        write_lock(path, pid, command)
        return
    except FileExistsError:
        pass

    existing = read_lock(path)
    existing_pid = existing.get("pid") if isinstance(existing, dict) else None
    if isinstance(existing_pid, int) and process_alive(existing_pid):
        raise SystemExit(f"Indexer lock is active at {path} for PID {existing_pid}")

    try:
        path.unlink()
    except FileNotFoundError:
        pass
    write_lock(path, pid, command)


def release_lock(path: Path, pid: int) -> None:
    existing = read_lock(path)
    if not isinstance(existing, dict) or existing.get("pid") != pid:
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def release_stale_lock(path: Path) -> bool:
    existing = read_lock(path)
    if not isinstance(existing, dict):
        return False
    pid = existing.get("pid")
    if isinstance(pid, int) and process_alive(pid):
        return False
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Coordinate a single native full-index process.")
    parser.add_argument("action", choices=("acquire", "release", "release-stale"))
    parser.add_argument("path")
    parser.add_argument("--pid", type=int, default=os.getpid())
    parser.add_argument("--command", default=" ".join(sys.argv))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    path = Path(args.path)
    if args.action == "acquire":
        acquire_lock(path, args.pid, args.command)
    elif args.action == "release":
        release_lock(path, args.pid)
    else:
        if release_stale_lock(path):
            print(f"Released stale index lock at {path}")


if __name__ == "__main__":
    main()
