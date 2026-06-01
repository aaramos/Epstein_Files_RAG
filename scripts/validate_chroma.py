from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from chroma_vector_diagnostics import inspect_chroma


def validate_diagnostics(payload: dict) -> None:
    if payload["embeddings"] <= 0:
        raise SystemExit("Chroma has no embeddings")
    if payload["vector_gap"] != 0 or not payload["vector_caught_up"]:
        raise SystemExit(
            "Chroma vector segment is not caught up: "
            f"gap={payload['vector_gap']}, embeddings={payload['embeddings']}"
        )


def validate_reader(path: Path, expected_count: int) -> None:
    import chromadb
    from chromadb.config import Settings

    client = chromadb.PersistentClient(
        path=str(path),
        settings=Settings(anonymized_telemetry=False),
    )
    collection = client.get_collection("langchain")
    count = collection.count()
    if count != expected_count:
        raise SystemExit(f"Chroma count mismatch: {count} != {expected_count}")

    collection.query(
        query_embeddings=[[0.0] * 384],
        n_results=1,
        include=["documents", "metadatas", "distances"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate that a Chroma HNSW index is readable and fully compacted.")
    parser.add_argument("--path", default="./chroma_db")
    args = parser.parse_args()

    path = Path(args.path)
    payload = inspect_chroma(path)
    validate_diagnostics(payload)
    validate_reader(path, payload["embeddings"])
    print(f"Chroma validation OK: {payload['embeddings']:,} vectors readable at {path}")


if __name__ == "__main__":
    main()
