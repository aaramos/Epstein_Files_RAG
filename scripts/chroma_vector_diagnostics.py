from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def inspect_chroma(path: Path) -> dict:
    db_path = path / "chroma.sqlite3"
    if not db_path.exists():
        raise SystemExit(f"Missing Chroma SQLite database at {db_path}")
    with sqlite3.connect(db_path) as connection:
        embeddings = connection.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        queue_count, queue_min, queue_max = connection.execute(
            "SELECT COUNT(*), MIN(seq_id), MAX(seq_id) FROM embeddings_queue"
        ).fetchone()
        segments = connection.execute(
            """
            SELECT segments.id, segments.scope, COALESCE(max_seq_id.seq_id, 0)
            FROM segments
            LEFT JOIN max_seq_id ON max_seq_id.segment_id = segments.id
            ORDER BY segments.scope
            """
        ).fetchall()
    vector_seq = max((seq for _, scope, seq in segments if scope == "VECTOR"), default=0)
    metadata_seq = max((seq for _, scope, seq in segments if scope == "METADATA"), default=0)
    return {
        "path": str(path),
        "embeddings": embeddings,
        "queue": {"count": queue_count, "min_seq_id": queue_min, "max_seq_id": queue_max},
        "segments": [
            {"id": segment_id, "scope": scope, "max_seq_id": seq}
            for segment_id, scope, seq in segments
        ],
        "vector_gap": max(0, int(metadata_seq) - int(vector_seq)),
        "vector_caught_up": vector_seq >= metadata_seq >= embeddings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect Chroma vector/metadata compaction state.")
    parser.add_argument("--path", default="./chroma_db")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = inspect_chroma(Path(args.path))
    if args.json:
        print(json.dumps(payload, indent=2))
        return
    print(f"Chroma path: {payload['path']}")
    print(f"Embeddings: {payload['embeddings']:,}")
    print(f"Queue rows: {payload['queue']['count']:,} ({payload['queue']['min_seq_id']}..{payload['queue']['max_seq_id']})")
    for segment in payload["segments"]:
        print(f"{segment['scope']} max_seq_id: {segment['max_seq_id']}")
    print(f"Vector gap: {payload['vector_gap']:,}")
    print("Vector caught up: " + ("yes" if payload["vector_caught_up"] else "no"))


if __name__ == "__main__":
    main()
