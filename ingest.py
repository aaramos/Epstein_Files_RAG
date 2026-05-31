import argparse
import hashlib
import json
import os
from pathlib import Path

os.environ["USE_TORCH"] = "1"

import pandas as pd
import pyarrow.parquet as pq
from dotenv import load_dotenv
from huggingface_hub import HfApi, hf_hub_download, snapshot_download
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from tqdm import tqdm

load_dotenv()

REPO_ID = "Nikity/Epstein-Files"
DATA_DIR = Path(os.getenv("DATA_PATH", "./data"))
DB_DIR = Path(os.getenv("DB_PATH", "./chroma_db"))
MANIFEST_PATH = Path(os.getenv("INGEST_MANIFEST_PATH", "./chroma_db/ingest_manifest.json"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
TEXT_COLUMNS = ("text_content", "text", "content")
FILENAME_COLUMNS = ("file_name", "original_filename", "filename", "source")


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
    files = [
        path for path in HfApi().list_repo_files(REPO_ID, repo_type="dataset")
        if path.endswith(".parquet")
    ]
    files.sort()
    return files[:limit] if limit else files


def download_data(num_files: int | None = 1, all_files: bool = False) -> list[Path]:
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
    schema_names = set(pq.ParquetFile(file_path).schema.names)
    text_col = next((column for column in TEXT_COLUMNS if column in schema_names), None)
    columns = [text_col] if text_col else []
    columns.extend(column for column in FILENAME_COLUMNS if column in schema_names)
    return text_col, columns


def process_parquet(file_path: Path) -> list[Document]:
    text_col, columns = available_columns(file_path)
    if not text_col:
        print(f"Skipping {file_path.name}: no text column found.")
        return []

    df = pd.read_parquet(file_path, columns=columns)
    filename_col = next((column for column in FILENAME_COLUMNS if column in df.columns), None)
    documents = []
    for row_number, row in enumerate(df.itertuples(index=False), start=1):
        row_data = row._asdict()
        text = str(row_data.get(text_col) or "").strip()
        if len(text) < 50:
            continue
        original_filename = row_data.get(filename_col) if filename_col else None
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
    return documents


def chunk_id(doc: Document, chunk_index: int) -> str:
    source = doc.metadata.get("source", "")
    row_number = doc.metadata.get("row_number", "")
    digest = hashlib.sha1(doc.page_content.encode("utf-8")).hexdigest()[:16]
    return f"{source}:{row_number}:{chunk_index}:{digest}"


def chunks_with_ids(documents: list[Document]) -> tuple[list[Document], list[str]]:
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


def index_files(file_paths: list[Path], batch_size: int) -> None:
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
        documents = process_parquet(file_path)
        chunks, ids = chunks_with_ids(documents)
        for start in tqdm(range(0, len(chunks), batch_size), desc=file_path.name, leave=False):
            end = start + batch_size
            vectorstore.add_documents(chunks[start:end], ids=ids[start:end])
        completed[file_path.name] = {"documents": len(documents), "chunks": len(chunks)}
        save_manifest(manifest)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download and index Epstein Files parquet data.")
    parser.add_argument("--all", action="store_true", help="Download and index every parquet file.")
    parser.add_argument("--num-files", type=int, default=1, help="Number of parquet files to download/index when not using --all.")
    parser.add_argument("--skip-download", action="store_true", help="Index already-downloaded files only.")
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("INGEST_BATCH_SIZE", "512")))
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.skip_download:
        files = sorted(DATA_DIR.glob("epstein_files-*.parquet"))
        if not args.all:
            files = files[: args.num_files]
    else:
        files = download_data(num_files=args.num_files, all_files=args.all)
    index_files(files, batch_size=args.batch_size)
