from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

os.environ["USE_TORCH"] = "1"

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import faiss_store
from ingest import chunks_with_ids, create_embeddings, iter_document_batches, local_parquet_files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a local FAISS HNSW vector index from downloaded parquet files.")
    parser.add_argument("--limit-files", type=int, help="Index only the first N parquet files for smoke testing.")
    parser.add_argument("--row-batch-size", type=int, default=int(os.getenv("PARQUET_ROW_BATCH_SIZE", "2048")))
    parser.add_argument("--chunk-batch-size", type=int, default=int(os.getenv("FAISS_CHUNK_BATCH_SIZE", "512")))
    parser.add_argument("--embedding-device", choices=("auto", "cpu", "mps"), default=os.getenv("EMBEDDING_DEVICE", "auto"))
    parser.add_argument("--output-dir", default=os.getenv("FAISS_INDEX_DIR", "./faiss_index"))
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing FAISS output directory.")
    return parser.parse_args()


def chunk_batches(files: list[Path], row_batch_size: int, chunk_batch_size: int):
    for file_path in files:
        for documents in iter_document_batches(file_path, row_batch_size=row_batch_size):
            chunks, chunk_ids = chunks_with_ids(documents)
            for start in range(0, len(chunks), chunk_batch_size):
                end = start + chunk_batch_size
                yield chunks[start:end], chunk_ids[start:end]


def main() -> None:
    args = parse_args()
    os.environ["EMBEDDING_DEVICE"] = args.embedding_device
    output_dir = Path(args.output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        if not args.overwrite:
            raise SystemExit(f"{output_dir} already exists and is not empty. Re-run with --overwrite to rebuild it.")
        shutil.rmtree(output_dir)
    files = local_parquet_files(limit=args.limit_files)
    if not files:
        raise SystemExit("No local parquet files found. Run the dataset download first.")
    embeddings = create_embeddings(device=args.embedding_device)
    payload = faiss_store.build_index(
        chunk_batches(files, args.row_batch_size, args.chunk_batch_size),
        embeddings=embeddings,
        root=output_dir,
    )
    print(f"FAISS index built at {output_dir.resolve()} with {payload['chunks']:,} chunks")


if __name__ == "__main__":
    main()
