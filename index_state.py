from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_EXPECTED_FILES = 634


@dataclass(frozen=True)
class IndexStatus:
    downloaded_files: int
    expected_files: int
    indexed_files: int
    in_progress_files: int
    indexed_docs: int
    indexed_chunks: int
    in_progress_names: tuple[str, ...]

    @property
    def indexing_active(self) -> bool:
        return self.in_progress_files > 0

    @property
    def complete(self) -> bool:
        return self.indexed_files >= self.expected_files and not self.indexing_active

    @property
    def partial(self) -> bool:
        return self.indexed_files < self.expected_files


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def expected_files() -> int:
    return int(os.getenv("EXPECTED_PARQUET_FILES", os.getenv("TOTAL_PARQUET_FILES", str(DEFAULT_EXPECTED_FILES))))


def default_data_dir(root: Path | None = None) -> Path:
    root = root or Path.cwd()
    return Path(os.getenv("DATA_PATH", str(root / "data")))


def default_manifest_path(root: Path | None = None) -> Path:
    root = root or Path.cwd()
    return Path(os.getenv("INGEST_MANIFEST_PATH", str(root / "chroma_db" / "ingest_manifest.json")))


def load_manifest(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {"completed_files": {}, "in_progress": {}}


def read_index_status(
    data_dir: Path | None = None,
    manifest_path: Path | None = None,
    expected_count: int | None = None,
    root: Path | None = None,
) -> IndexStatus:
    root = root or Path.cwd()
    data_dir = data_dir or default_data_dir(root)
    manifest_path = manifest_path or default_manifest_path(root)
    expected_count = expected_count or expected_files()

    manifest = load_manifest(manifest_path)
    completed = manifest.get("completed_files", {})
    in_progress = manifest.get("in_progress", {})
    downloaded_files = len(list(data_dir.glob("epstein_files-*.parquet")))
    indexed_docs = sum(item.get("documents", 0) for item in completed.values() if isinstance(item, dict))
    indexed_chunks = sum(item.get("chunks", 0) for item in completed.values() if isinstance(item, dict))

    return IndexStatus(
        downloaded_files=downloaded_files,
        expected_files=expected_count,
        indexed_files=len(completed),
        in_progress_files=len(in_progress),
        indexed_docs=indexed_docs,
        indexed_chunks=indexed_chunks,
        in_progress_names=tuple(sorted(in_progress)),
    )


def query_enabled(status: IndexStatus, allow_during_index: bool = False) -> bool:
    return bool(status.indexed_chunks) and (allow_during_index or status.complete)
