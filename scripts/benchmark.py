from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

os.environ["USE_TORCH"] = "1"

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from index_state import DEFAULT_EXPECTED_FILES, read_index_status
from rag_chain import get_rag_chain, get_vectorstore


DEFAULT_QUERIES = (
    "What aircraft are mentioned in the Epstein documents?",
    "Which documents discuss flight logs?",
    "What locations are associated with Epstein travel?",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark retrieval and optional RAG generation.")
    parser.add_argument("--query", action="append", help="Query to benchmark. Can be repeated.")
    parser.add_argument("--rag", action="store_true", help="Also benchmark LLM generation.")
    parser.add_argument("--provider", default=os.getenv("LLM_PROVIDER", "OMLX"))
    parser.add_argument("--model", default=os.getenv("OMLX_MODEL") or os.getenv("MORNING_DISPATCH_LIBRARIAN_MODEL", "Gemma4-MTP-26B-BF16"))
    parser.add_argument("--allow-active-index", action="store_true", help="Allow querying Chroma while ingestion is actively writing.")
    parser.add_argument("--expected-files", type=int, default=int(os.getenv("EXPECTED_PARQUET_FILES", str(DEFAULT_EXPECTED_FILES))))
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser.parse_args()


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    index = min(len(values) - 1, max(0, round((len(values) - 1) * pct)))
    return values[index]


def collection_count(vectorstore) -> int | None:
    try:
        return int(vectorstore._collection.count())
    except Exception:
        return None


def validate_safe_to_query(expected_files: int, allow_active_index: bool) -> None:
    status = read_index_status(expected_count=expected_files, root=ROOT)
    if status.indexing_active and not allow_active_index:
        raise SystemExit(
            "Indexing is active; skipping benchmark Chroma reads to avoid read/write errors. "
            "Use --allow-active-index only for intentional stress testing."
        )


def run_retrieval(query: str) -> dict:
    vectorstore = get_vectorstore()
    start = time.perf_counter()
    docs = vectorstore.as_retriever(
        search_type="mmr",
        search_kwargs={
            "k": int(os.getenv("RETRIEVER_K", "12")),
            "fetch_k": int(os.getenv("RETRIEVER_FETCH_K", "80")),
        },
    ).invoke(query)
    elapsed = time.perf_counter() - start
    return {
        "query": query,
        "seconds": elapsed,
        "docs": len(docs),
        "sources": [doc.metadata.get("source", "unknown") for doc in docs[:5]],
    }


def run_rag(query: str, provider: str, model: str) -> dict:
    chain = get_rag_chain(provider=provider, model_name=model)
    start = time.perf_counter()
    response = chain.invoke({"input": query})
    elapsed = time.perf_counter() - start
    answer = response.get("answer", "")
    context = response.get("context") or []
    return {
        "query": query,
        "seconds": elapsed,
        "context_docs": len(context),
        "answer_chars": len(answer),
        "answer_preview": answer[:300],
    }


def summarize(results: list[dict]) -> dict:
    seconds = [item["seconds"] for item in results]
    return {
        "count": len(results),
        "mean_seconds": statistics.mean(seconds) if seconds else None,
        "p50_seconds": percentile(seconds, 0.5),
        "p95_seconds": percentile(seconds, 0.95),
    }


def main() -> None:
    args = parse_args()
    validate_safe_to_query(args.expected_files, args.allow_active_index)
    queries = tuple(args.query or DEFAULT_QUERIES)
    vectorstore = get_vectorstore()
    retrieval = [run_retrieval(query) for query in queries]
    payload = {
        "vector_records": collection_count(vectorstore),
        "retrieval": retrieval,
        "retrieval_summary": summarize(retrieval),
    }
    if args.rag:
        rag = [run_rag(query, args.provider, args.model) for query in queries]
        payload["rag"] = rag
        payload["rag_summary"] = summarize(rag)

    if args.json:
        print(json.dumps(payload, indent=2))
        return

    print(f"Vector records: {payload['vector_records']}")
    for item in retrieval:
        print(f"retrieval {item['seconds']:.2f}s | docs={item['docs']} | {item['query']}")
    print(f"retrieval mean: {payload['retrieval_summary']['mean_seconds']:.2f}s")
    if args.rag:
        for item in payload["rag"]:
            print(f"rag {item['seconds']:.2f}s | context={item['context_docs']} | chars={item['answer_chars']} | {item['query']}")
        print(f"rag mean: {payload['rag_summary']['mean_seconds']:.2f}s")


if __name__ == "__main__":
    main()
