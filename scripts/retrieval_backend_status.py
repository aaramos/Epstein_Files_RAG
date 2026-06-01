from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import faiss_store
import rag_chain


def selected_backend() -> dict:
    configured = os.getenv("RETRIEVER_BACKEND", "auto").lower()
    faiss_ready = faiss_store.available()
    chroma_has_gap = rag_chain._has_uncompacted_vector_wal()

    if configured == "faiss":
        selected = "faiss_hnsw"
        reason = "forced by RETRIEVER_BACKEND"
    elif configured in {"sqlite", "sqlite_fts", "fts"}:
        selected = "sqlite_fts"
        reason = "forced by RETRIEVER_BACKEND"
    elif configured == "auto" and faiss_ready:
        selected = "faiss_hnsw"
        reason = "completed FAISS index is available"
    elif configured == "auto" and chroma_has_gap:
        selected = "sqlite_fts"
        reason = "Chroma vector segment is behind metadata"
    elif configured == "auto":
        selected = "chroma_hnsw"
        reason = "FAISS unavailable and Chroma has no detected vector gap"
    else:
        selected = "chroma_hnsw"
        reason = f"unknown RETRIEVER_BACKEND={configured!r}; retrieval code will attempt Chroma"

    return {
        "configured": configured,
        "selected": selected,
        "reason": reason,
        "faiss_available": faiss_ready,
        "chroma_has_uncompacted_vector_wal": chroma_has_gap,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Report which retrieval backend the app will choose.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = selected_backend()
    if args.json:
        print(json.dumps(payload, indent=2))
        return

    print(f"Configured backend: {payload['configured']}")
    print(f"Selected backend: {payload['selected']}")
    print(f"Reason: {payload['reason']}")
    print(f"FAISS available: {'yes' if payload['faiss_available'] else 'no'}")
    print("Chroma vector gap detected: " + ("yes" if payload["chroma_has_uncompacted_vector_wal"] else "no"))


if __name__ == "__main__":
    main()
