from __future__ import annotations

import argparse
import json
import subprocess
import sqlite3
import time
from pathlib import Path


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def expected_chunks_from_chroma_manifest(path: Path) -> int | None:
    manifest = load_json(path)
    completed = manifest.get("completed_files")
    if not isinstance(completed, dict):
        return None
    return sum(int(item.get("chunks", 0)) for item in completed.values())


def sqlite_progress(path: Path) -> dict:
    db_path = path / "chunks.sqlite3"
    if not db_path.exists():
        return {}
    with sqlite3.connect(db_path) as connection:
        total, max_id = connection.execute("SELECT COUNT(*), MAX(id) FROM chunks").fetchone()
        by_source = connection.execute(
            """
            SELECT source, COUNT(*) AS chunks
            FROM chunks
            GROUP BY source
            ORDER BY source DESC
            LIMIT 1
            """
        ).fetchone()
    return {
        "metadata_chunks": int(total or 0),
        "max_id": int(max_id) if max_id is not None else None,
        "last_source": by_source[0] if by_source else None,
        "last_source_chunks": int(by_source[1]) if by_source else None,
    }


def build_elapsed_seconds(pid_path: Path) -> float | None:
    try:
        pid = int(pid_path.read_text().strip())
    except (OSError, ValueError):
        return None
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "lstart="],
        text=True,
        capture_output=True,
        check=False,
    )
    started = result.stdout.strip()
    if result.returncode != 0 or not started:
        return None
    try:
        return max(0.0, time.time() - time.mktime(time.strptime(started, "%a %b %d %H:%M:%S %Y")))
    except ValueError:
        return None


def payload(root: Path, chroma_manifest: Path, pid_path: Path | None = None) -> dict:
    manifest = load_json(root / "manifest.json")
    expected = expected_chunks_from_chroma_manifest(chroma_manifest)
    progress = sqlite_progress(root)
    chunks = int(manifest.get("chunks") or progress.get("metadata_chunks") or 0)
    elapsed = build_elapsed_seconds(pid_path) if pid_path else None
    chunks_per_second = (chunks / elapsed) if elapsed and chunks else None
    remaining_seconds = ((expected - chunks) / chunks_per_second) if expected and chunks_per_second else None
    result = {
        "path": str(root),
        "chunks": chunks,
        "complete": manifest.get("complete") is True,
        "expected_chunks": expected,
        "fraction": (chunks / expected) if expected else None,
        "elapsed_seconds": elapsed,
        "chunks_per_second": chunks_per_second,
        "eta_seconds": remaining_seconds,
    }
    result.update(progress)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Report local FAISS index build progress.")
    parser.add_argument("--path", default="./faiss_index")
    parser.add_argument("--chroma-manifest", default="./chroma_db/ingest_manifest.json")
    parser.add_argument("--pid-file", default="./runtime/faiss_build.pid")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    data = payload(Path(args.path), Path(args.chroma_manifest), Path(args.pid_file))
    if args.json:
        print(json.dumps(data, indent=2))
        return
    print(f"FAISS path: {data['path']}")
    print(f"Chunks: {data['chunks']:,}")
    if data["expected_chunks"]:
        print(f"Expected chunks: {data['expected_chunks']:,}")
        print(f"Progress: {data['fraction']:.1%}")
    if data.get("chunks_per_second"):
        print(f"Rate: {data['chunks_per_second']:.1f} chunks/sec")
    if data.get("eta_seconds"):
        hours = data["eta_seconds"] / 3600
        print(f"ETA: {hours:.1f} hours")
    print("Complete: " + ("yes" if data["complete"] else "no"))
    if data.get("last_source"):
        print(f"Latest source: {data['last_source']} ({data['last_source_chunks']:,} chunks)")


if __name__ == "__main__":
    main()
