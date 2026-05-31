from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

os.environ["USE_TORCH"] = "1"

from dotenv import load_dotenv

if TYPE_CHECKING:
    from langchain_core.documents import Document

load_dotenv()

REPO_ID = "Nikity/Epstein-Files"
DATA_DIR = Path(os.getenv("DATA_PATH", "./data"))
DB_DIR = Path(os.getenv("DB_PATH", "./chroma_db"))
MANIFEST_PATH = Path(os.getenv("INGEST_MANIFEST_PATH", "./chroma_db/ingest_manifest.json"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
TEXT_COLUMNS = ("text_content", "text", "content")
FILENAME_COLUMNS = ("file_name", "original_filename", "filename", "source")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def embedding_device() -> str:
    configured = os.getenv("EMBEDDING_DEVICE", "auto").lower()
    if configured != "auto":
        return configured
    try:
        import torch
        if torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def load_manifest() -> dict:
    try:
        return json.loads(MANIFEST_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {"completed_files": {}}


def save_manifest(manifest: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True))


def parquet_files_from_hub(limit: int | None = None) -> list[str]:
    from huggingface_hub import HfApi

    files = [
        path for path in HfApi().list_repo_files(REPO_ID, repo_type="dataset")
        if path.endswith(".parquet")
    ]
    files.sort()
    return files[:limit] if limit else files


def download_data(num_files: int | None = 1, all_files: bool = False) -> list[Path]:
    from huggingface_hub import hf_hub_download, snapshot_download

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if all_files:
        snapshot_download(
            repo_id=REPO_ID,
            repo_type="dataset",
            local_dir=str(DATA_DIR),
            allow_patterns="*.parquet",
            max_workers=int(os.getenv("HF_DOWNLOAD_WORKERS", "8")),
        )
        return sorted(DATA_DIR.glob("epstein_files-*.parquet"))

    files = parquet_files_from_hub(limit=num_files)
    paths = []
    for filename in files:
        local_path = DATA_DIR / filename
        if not local_path.exists():
            hf_hub_download(
                repo_id=REPO_ID,
                filename=filename,
                repo_type="dataset",
                local_dir=str(DATA_DIR),
            )
        paths.append(local_path)
    return paths


def available_columns(file_path: Path) -> tuple[str | None, list[str]]:
    import pyarrow.parquet as pq

    schema_names = set(pq.ParquetFile(file_path).schema.names)
    text_col = next((column for column in TEXT_COLUMNS if column in schema_names), None)
    columns = [text_col] if text_col else []
    columns.extend(column for column in FILENAME_COLUMNS if column in schema_names)
    return text_col, columns


def process_parquet(file_path: Path) -> list[Document]:
    documents = []
    for batch in iter_document_batches(file_path):
        documents.extend(batch)
    return documents


def iter_document_batches(file_path: Path, row_batch_size: int | None = None):
    import pyarrow.parquet as pq
    from langchain_core.documents import Document

    text_col, columns = available_columns(file_path)
    if not text_col:
        print(f"Skipping {file_path.name}: no text column found.")
        return

    parquet_file = pq.ParquetFile(file_path)
    batch_size = row_batch_size or int(os.getenv("PARQUET_ROW_BATCH_SIZE", "2048"))
    row_offset = 0
    for record_batch in parquet_file.iter_batches(batch_size=batch_size, columns=columns):
        batch = record_batch.to_pydict()
        filename_col = next((column for column in FILENAME_COLUMNS if column in batch), None)
        documents = []
        for index, text_value in enumerate(batch.get(text_col, []), start=1):
            row_number = row_offset + index
            text = str(text_value or "").strip()
            if len(text) < 50:
                continue
            original_filename = batch[filename_col][index - 1] if filename_col else None
            documents.append(
                Document(
                    page_content=text,
                    metadata={
                        "source": file_path.name,
                        "row_number": row_number,
                        "original_filename": original_filename or "unknown",
                    },
                )
            )
        row_offset += record_batch.num_rows
        if documents:
            yield documents


def chunk_id(doc: Document, chunk_index: int) -> str:
    source = doc.metadata.get("source", "")
    row_number = doc.metadata.get("row_number", "")
    digest = hashlib.sha1(doc.page_content.encode("utf-8")).hexdigest()[:16]
    return f"{source}:{row_number}:{chunk_index}:{digest}"


def chunks_with_ids(documents: list[Document]) -> tuple[list[Document], list[str]]:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=int(os.getenv("CHUNK_SIZE", "1000")),
        chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "100")),
    )
    chunks = splitter.split_documents(documents)
    ids_by_row = {}
    ids = []
    for chunk in chunks:
        key = (chunk.metadata.get("source"), chunk.metadata.get("row_number"))
        index = ids_by_row.get(key, 0)
        ids_by_row[key] = index + 1
        ids.append(chunk_id(chunk, index))
    return chunks, ids


def delete_partial_file(vectorstore, file_name: str) -> None:
    try:
        vectorstore._collection.delete(where={"source": file_name})
    except Exception:
        pass


def index_files(file_paths: list[Path], batch_size: int, row_batch_size: int | None = None) -> None:
    from langchain_chroma import Chroma
    from langchain_huggingface import HuggingFaceEmbeddings
    from tqdm import tqdm

    manifest = load_manifest()
    completed = manifest.setdefault("completed_files", {})
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": embedding_device()},
        encode_kwargs={"batch_size": int(os.getenv("EMBEDDING_BATCH_SIZE", "64"))},
    )
    vectorstore = Chroma(
        persist_directory=str(DB_DIR),
        embedding_function=embeddings,
    )

    for file_path in tqdm(file_paths, desc="Indexing parquet files"):
        if completed.get(file_path.name):
            continue
        delete_partial_file(vectorstore, file_path.name)
        manifest.setdefault("in_progress", {})[file_path.name] = {"started_at": utc_now()}
        save_manifest(manifest)

        document_count = 0
        chunk_count = 0
        for documents in tqdm(iter_document_batches(file_path, row_batch_size=row_batch_size), desc=file_path.name, leave=False):
            chunks, ids = chunks_with_ids(documents)
            document_count += len(documents)
            chunk_count += len(chunks)
            for start in range(0, len(chunks), batch_size):
                end = start + batch_size
                vectorstore.add_documents(chunks[start:end], ids=ids[start:end])
        completed[file_path.name] = {
            "documents": document_count,
            "chunks": chunk_count,
            "indexed_at": utc_now(),
            "bytes": file_path.stat().st_size if file_path.exists() else None,
        }
        manifest.get("in_progress", {}).pop(file_path.name, None)
        save_manifest(manifest)


def local_parquet_files(limit: int | None = None) -> list[Path]:
    files = sorted(DATA_DIR.glob("epstein_files-*.parquet"))
    return files[:limit] if limit else files


def print_status(check_hub: bool = False) -> None:
    manifest = load_manifest()
    completed = manifest.get("completed_files", {})
    in_progress = manifest.get("in_progress", {})
    local_files = local_parquet_files()
    indexed_docs = sum(item.get("documents", 0) for item in completed.values())
    indexed_chunks = sum(item.get("chunks", 0) for item in completed.values())
    print(f"Data dir: {DATA_DIR}")
    print(f"DB dir: {DB_DIR}")
    print(f"Local parquet files: {len(local_files)}")
    print(f"Indexed parquet files: {len(completed)}")
    print(f"In-progress parquet files: {len(in_progress)}")
    print(f"Indexed documents: {indexed_docs}")
    print(f"Indexed chunks: {indexed_chunks}")
    if check_hub:
        total = len(parquet_files_from_hub())
        print(f"Hub parquet files: {total}")
        if total:
            print(f"Download progress: {len(local_files)}/{total} ({len(local_files) / total:.1%})")
            print(f"Index progress: {len(completed)}/{total} ({len(completed) / total:.1%})")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download and index Epstein Files parquet data.")
    parser.add_argument("--all", action="store_true", help="Download and index every parquet file.")
    parser.add_argument("--num-files", type=int, default=1, help="Number of parquet files to download/index when not using --all.")
    parser.add_argument("--skip-download", action="store_true", help="Index already-downloaded files only.")
    parser.add_argument("--download-only", action="store_true", help="Download parquet files without indexing them.")
    parser.add_argument("--status", action="store_true", help="Print local download/index status and exit.")
    parser.add_argument("--check-hub", action="store_true", help="Include Hugging Face file counts in --status output.")
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("INGEST_BATCH_SIZE", "512")))
    parser.add_argument("--row-batch-size", type=int, default=int(os.getenv("PARQUET_ROW_BATCH_SIZE", "2048")), help="Parquet rows to stream at a time.")
    parser.add_argument("--embedding-device", choices=("auto", "cpu", "mps"), help="Override EMBEDDING_DEVICE for this run.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.embedding_device:
        os.environ["EMBEDDING_DEVICE"] = args.embedding_device
    if args.status:
        print_status(check_hub=args.check_hub)
        raise SystemExit(0)
    if args.skip_download:
        files = local_parquet_files()
        if not args.all:
            files = files[: args.num_files]
    else:
        files = download_data(num_files=args.num_files, all_files=args.all)
    if args.download_only:
        print(f"Downloaded/available parquet files: {len(files)}")
    else:
        index_files(files, batch_size=args.batch_size, row_batch_size=args.row_batch_size)
