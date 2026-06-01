from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.faiss_progress import payload
from scripts.validate_rag import DEFAULT_QUERY


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate that the local FAISS backend is complete and retrievable.")
    parser.add_argument("--path", default=os.getenv("FAISS_INDEX_DIR", "./faiss_index"))
    parser.add_argument("--chroma-manifest", default="./chroma_db/ingest_manifest.json")
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--min-docs", type=int, default=3)
    parser.add_argument("--skip-retrieval", action="store_true")
    return parser.parse_args()


def validate_complete(index_path: Path, chroma_manifest: Path) -> dict:
    data = payload(index_path, chroma_manifest)
    print(f"FAISS chunks: {data['chunks']:,}")
    if data.get("expected_chunks"):
        print(f"Expected chunks: {data['expected_chunks']:,}")
    print("Complete: " + ("yes" if data["complete"] else "no"))
    if not data["complete"]:
        raise SystemExit("FAISS index is not marked complete yet")
    if data.get("expected_chunks") and data["chunks"] != data["expected_chunks"]:
        raise SystemExit("FAISS chunk count does not match the completed Chroma ingest manifest")
    if data.get("metadata_chunks") is not None and data["metadata_chunks"] != data["chunks"]:
        raise SystemExit("FAISS metadata row count does not match the manifest chunk count")
    return data


def validate_retrieval(index_path: Path, query: str, min_docs: int) -> None:
    env = os.environ.copy()
    env["FAISS_INDEX_DIR"] = str(index_path)
    env["RETRIEVER_BACKEND"] = "faiss"
    command = [
        sys.executable,
        "scripts/validate_rag.py",
        "--query",
        query,
        "--min-docs",
        str(min_docs),
        "--allow-active-index",
    ]
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def main() -> None:
    args = parse_args()
    index_path = Path(args.path)
    validate_complete(index_path, Path(args.chroma_manifest))
    if not args.skip_retrieval:
        validate_retrieval(index_path, args.query, args.min_docs)


if __name__ == "__main__":
    main()
