from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ["USE_TORCH"] = "1"

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from index_state import DEFAULT_EXPECTED_FILES, read_index_status
from rag_chain import collection_record_count, get_rag_chain, get_retriever


DEFAULT_QUERY = "What is the name of the aircraft used by Epstein?"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate local Chroma retrieval and optional oMLX RAG generation.")
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--min-docs", type=int, default=3)
    parser.add_argument("--rag", action="store_true", help="Also call the configured LLM and generate an answer.")
    parser.add_argument("--provider", default=os.getenv("LLM_PROVIDER", "OMLX"))
    parser.add_argument("--model", default=os.getenv("OMLX_MODEL") or os.getenv("MORNING_DISPATCH_LIBRARIAN_MODEL", "Gemma4-MTP-26B-BF16"))
    parser.add_argument("--require-full-index", action="store_true", help="Fail unless every expected parquet file is indexed and no file is in progress.")
    parser.add_argument("--allow-active-index", action="store_true", help="Allow querying Chroma while ingestion is actively writing.")
    parser.add_argument("--expected-files", type=int, default=int(os.getenv("EXPECTED_PARQUET_FILES", str(DEFAULT_EXPECTED_FILES))))
    return parser.parse_args()


def validate_full_index(expected_files: int) -> None:
    status = read_index_status(expected_count=expected_files, root=ROOT)
    print(f"Indexed files: {status.indexed_files}/{expected_files}")
    print(f"In-progress files: {status.in_progress_files}")
    if not status.complete:
        raise SystemExit("Full index is not complete yet")


def validate_safe_to_query(expected_files: int, allow_active_index: bool) -> None:
    status = read_index_status(expected_count=expected_files, root=ROOT)
    if status.indexing_active and not allow_active_index:
        raise SystemExit(
            "Indexing is active; skipping Chroma reads to avoid read/write errors. "
            "Use --allow-active-index only for intentional stress testing."
        )


def validate_retrieval(query: str, min_docs: int) -> list:
    count = collection_record_count()
    print(f"Vector records: {count if count is not None else 'unknown'}")
    docs = get_retriever().invoke({"input": query})
    print(f"Retrieved docs: {len(docs)}")
    for index, doc in enumerate(docs[: min(5, len(docs))], start=1):
        source = doc.metadata.get("source", "unknown")
        original = doc.metadata.get("original_filename", "unknown")
        preview = " ".join(doc.page_content.split())[:160]
        print(f"{index}. {source} | {original} | {preview}")
    if len(docs) < min_docs:
        raise SystemExit(f"Expected at least {min_docs} retrieved docs, got {len(docs)}")
    return docs


def validate_rag(query: str, provider: str, model: str) -> None:
    chain = get_rag_chain(provider=provider, model_name=model)
    response = chain.invoke({"input": query})
    answer = response.get("answer", "")
    context = response.get("context") or []
    print(f"RAG context docs: {len(context)}")
    print("Answer preview:")
    print(answer[:1000])
    if not answer.strip():
        raise SystemExit("RAG answer was empty")
    if not context:
        raise SystemExit("RAG response had no retrieved context")


if __name__ == "__main__":
    args = parse_args()
    if args.require_full_index:
        validate_full_index(args.expected_files)
    validate_safe_to_query(args.expected_files, args.allow_active_index)
    validate_retrieval(args.query, args.min_docs)
    if args.rag:
        validate_rag(args.query, args.provider, args.model)
    print("Validation OK")
