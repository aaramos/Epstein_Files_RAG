from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.faiss_progress import payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Wait for FAISS index completion and optionally validate retrieval.")
    parser.add_argument("--path", default="./faiss_index")
    parser.add_argument("--chroma-manifest", default="./chroma_db/ingest_manifest.json")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--once", action="store_true", help="Print one status update and exit.")
    parser.add_argument("--validate", action="store_true", help="Run scripts/validate_faiss.py when complete.")
    return parser.parse_args()


def print_status(data: dict) -> None:
    chunks = int(data.get("chunks") or 0)
    expected = data.get("expected_chunks")
    complete = data.get("complete") is True
    if expected:
        print(f"FAISS: {chunks:,}/{expected:,} chunks ({chunks / expected:.1%}), complete={complete}", flush=True)
    else:
        print(f"FAISS: {chunks:,} chunks, complete={complete}", flush=True)
    if data.get("last_source"):
        print(f"Latest source: {data['last_source']} ({data.get('last_source_chunks', 0):,} chunks)", flush=True)


def run_validation(path: Path, chroma_manifest: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "scripts/validate_faiss.py",
            "--path",
            str(path),
            "--chroma-manifest",
            str(chroma_manifest),
        ],
        cwd=ROOT,
        check=True,
    )


def main() -> None:
    args = parse_args()
    path = Path(args.path)
    chroma_manifest = Path(args.chroma_manifest)
    while True:
        data = payload(path, chroma_manifest)
        print_status(data)
        if args.once:
            return
        if data.get("complete") is True:
            if args.validate:
                run_validation(path, chroma_manifest)
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
