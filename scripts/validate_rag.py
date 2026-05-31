from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ["USE_TORCH"] = "1"

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag_chain import get_rag_chain, get_vectorstore


DEFAULT_QUERY = "What is the name of the aircraft used by Epstein?"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate local Chroma retrieval and optional oMLX RAG generation.")
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--min-docs", type=int, default=3)
    parser.add_argument("--rag", action="store_true", help="Also call the configured LLM and generate an answer.")
    parser.add_argument("--provider", default=os.getenv("LLM_PROVIDER", "OMLX"))
    parser.add_argument("--model", default=os.getenv("OMLX_MODEL") or os.getenv("MORNING_DISPATCH_LIBRARIAN_MODEL", "Gemma4-MTP-26B-BF16"))
    return parser.parse_args()


def validate_retrieval(query: str, min_docs: int) -> list:
    vectorstore = get_vectorstore()
    try:
        count = vectorstore._collection.count()
    except Exception:
        count = None
    print(f"Vector records: {count if count is not None else 'unknown'}")
    docs = vectorstore.as_retriever(
        search_type="mmr",
        search_kwargs={
            "k": max(min_docs, int(os.getenv("RETRIEVER_K", "12"))),
            "fetch_k": int(os.getenv("RETRIEVER_FETCH_K", "80")),
        },
    ).invoke(query)
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
    validate_retrieval(args.query, args.min_docs)
    if args.rag:
        validate_rag(args.query, args.provider, args.model)
    print("Validation OK")
