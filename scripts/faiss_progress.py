from __future__ import annotations

import argparse
import json
import sqlite3
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


def payload(root: Path, chroma_manifest: Path) -> dict:
    manifest = load_json(root / "manifest.json")
    expected = expected_chunks_from_chroma_manifest(chroma_manifest)
    progress = sqlite_progress(root)
    chunks = int(manifest.get("chunks") or progress.get("metadata_chunks") or 0)
    result = {
        "path": str(root),
        "chunks": chunks,
        "complete": manifest.get("complete") is True,
        "expected_chunks": expected,
        "fraction": (chunks / expected) if expected else None,
    }
    result.update(progress)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Report local FAISS index build progress.")
    parser.add_argument("--path", default="./faiss_index")
    parser.add_argument("--chroma-manifest", default="./chroma_db/ingest_manifest.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    data = payload(Path(args.path), Path(args.chroma_manifest))
    if args.json:
        print(json.dumps(data, indent=2))
        return
    print(f"FAISS path: {data['path']}")
    print(f"Chunks: {data['chunks']:,}")
    if data["expected_chunks"]:
        print(f"Expected chunks: {data['expected_chunks']:,}")
        print(f"Progress: {data['fraction']:.1%}")
    print("Complete: " + ("yes" if data["complete"] else "no"))
    if data.get("last_source"):
        print(f"Latest source: {data['last_source']} ({data['last_source_chunks']:,} chunks)")


if __name__ == "__main__":
    main()
