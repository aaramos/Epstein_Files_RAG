from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Iterable

import numpy as np
from langchain_core.documents import Document


DEFAULT_FAISS_DIR = Path(os.getenv("FAISS_INDEX_DIR", "./faiss_index"))
INDEX_FILENAME = "index.faiss"
METADATA_FILENAME = "chunks.sqlite3"
MANIFEST_FILENAME = "manifest.json"


def _load_faiss():
    import faiss

    threads = int(os.getenv("FAISS_NUM_THREADS", "1"))
    if threads > 0:
        faiss.omp_set_num_threads(threads)
    return faiss


def faiss_dir() -> Path:
    return Path(os.getenv("FAISS_INDEX_DIR", str(DEFAULT_FAISS_DIR)))


def index_path(root: Path | None = None) -> Path:
    return (root or faiss_dir()) / INDEX_FILENAME


def metadata_path(root: Path | None = None) -> Path:
    return (root or faiss_dir()) / METADATA_FILENAME


def manifest_path(root: Path | None = None) -> Path:
    return (root or faiss_dir()) / MANIFEST_FILENAME


def available(root: Path | None = None) -> bool:
    root = root or faiss_dir()
    return (
        index_path(root).exists()
        and metadata_path(root).exists()
        and load_manifest(root).get("complete") is True
    )


def load_manifest(root: Path | None = None) -> dict:
    try:
        return json.loads(manifest_path(root).read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _connect(root: Path | None = None) -> sqlite3.Connection:
    connection = sqlite3.connect(metadata_path(root))
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY,
            chunk_id TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            row_number INTEGER NOT NULL,
            content TEXT NOT NULL
        )
        """
    )
    return connection


def _next_id(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT COALESCE(MAX(id), -1) + 1 FROM chunks").fetchone()
    return int(row[0])


def _as_float32(vectors: list[list[float]]) -> np.ndarray:
    return np.asarray(vectors, dtype="float32")


def build_index(
    chunk_batches: Iterable[tuple[list[Document], list[str]]],
    embeddings,
    root: Path | None = None,
    hnsw_m: int | None = None,
    persist_every: int | None = None,
) -> dict:
    root = root or faiss_dir()
    root.mkdir(parents=True, exist_ok=True)
    hnsw_m = hnsw_m or int(os.getenv("FAISS_HNSW_M", "32"))
    persist_every = persist_every or int(os.getenv("FAISS_PERSIST_EVERY", "10000"))

    connection = _connect(root)
    index = None
    total_chunks = 0
    next_id = _next_id(connection)

    for documents, chunk_ids in chunk_batches:
        if not documents:
            continue
        vectors = _as_float32(embeddings.embed_documents([doc.page_content for doc in documents]))
        if index is None:
            faiss = _load_faiss()
            index = faiss.IndexHNSWFlat(vectors.shape[1], hnsw_m)

        ids = np.arange(next_id, next_id + len(documents), dtype="int64")
        index.add(vectors)
        rows = [
            (
                int(row_id),
                chunk_id,
                doc.metadata.get("source", "unknown"),
                doc.metadata.get("original_filename", "unknown"),
                int(doc.metadata.get("row_number") or 0),
                doc.page_content,
            )
            for row_id, chunk_id, doc in zip(ids, chunk_ids, documents)
        ]
        connection.executemany(
            """
            INSERT OR REPLACE INTO chunks
                (id, chunk_id, source, original_filename, row_number, content)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        connection.commit()
        total_chunks += len(documents)
        next_id += len(documents)
        if total_chunks % persist_every < len(documents):
            faiss.write_index(index, str(index_path(root)))
            manifest_path(root).write_text(json.dumps({"chunks": int(index.ntotal), "complete": False}, indent=2))

    if index is None:
        raise ValueError("No chunks were provided to build the FAISS index")

    faiss.write_index(index, str(index_path(root)))
    payload = {"chunks": int(index.ntotal), "backend": "faiss_hnsw", "complete": True}
    manifest_path(root).write_text(json.dumps(payload, indent=2))
    connection.close()
    return payload


def search(query: str, k: int, embeddings, root: Path | None = None) -> list[Document]:
    root = root or faiss_dir()
    if not available(root):
        return []
    query_vector = _as_float32([embeddings.embed_query(query)])
    faiss = _load_faiss()
    index = faiss.read_index(str(index_path(root)))
    distances, labels = index.search(query_vector, k)
    ids = [int(label) for label in labels[0] if int(label) >= 0]
    if not ids:
        return []

    placeholders = ",".join("?" for _ in ids)
    with _connect(root) as connection:
        rows = connection.execute(
            f"""
            SELECT id, source, original_filename, row_number, content
            FROM chunks
            WHERE id IN ({placeholders})
            """,
            ids,
        ).fetchall()
    by_id = {int(row[0]): row for row in rows}
    docs = []
    for row_id in ids:
        row = by_id.get(row_id)
        if not row:
            continue
        _, source, original_filename, row_number, content = row
        docs.append(
            Document(
                page_content=content,
                metadata={
                    "source": source,
                    "original_filename": original_filename,
                    "row_number": row_number,
                    "retrieval_backend": "faiss_hnsw",
                },
            )
        )
    return docs
