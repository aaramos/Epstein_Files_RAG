from __future__ import annotations

import json
import os
import shutil
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DATA_DIR = Path(os.getenv("DATA_PATH", str(ROOT / "data")))
DB_DIR = Path(os.getenv("DB_PATH", str(ROOT / "chroma_db")))
MANIFEST_PATH = Path(os.getenv("INGEST_MANIFEST_PATH", str(DB_DIR / "ingest_manifest.json")))

from index_state import load_manifest, read_index_status
from llm_factory import get_omlx_base_url, get_omlx_model_name


def status(label: str, ok: bool, detail: str) -> None:
    marker = "OK" if ok else "WARN"
    print(f"[{marker}] {label}: {detail}")


def command_exists(name: str) -> bool:
    for directory in os.getenv("PATH", "").split(os.pathsep):
        if (Path(directory) / name).exists():
            return True
    return False


def read_omlx_key() -> str | None:
    for name in ("MORNING_DISPATCH_MODEL_API_KEY", "OMLX_API_KEY", "LM_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        value = os.getenv(name)
        if value:
            return value
    settings_path = Path(os.getenv("OMLX_SETTINGS_PATH", "~/.omlx/settings.json")).expanduser()
    return load_manifest(settings_path).get("auth", {}).get("api_key")


def check_python() -> None:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    status("Python", sys.version_info[:2] >= (3, 11), version)


def check_imports() -> None:
    required = ("streamlit", "langchain", "chromadb", "sentence_transformers", "pyarrow", "torch")
    missing = []
    for module in required:
        try:
            __import__(module)
        except Exception:
            missing.append(module)
    status("Python packages", not missing, "all present" if not missing else "missing " + ", ".join(missing))


def check_mps() -> None:
    try:
        import torch
        available = bool(torch.backends.mps.is_available())
        detail = "available" if available else "not available; CPU fallback will be used"
        status("Apple Silicon MPS", True, detail)
    except Exception as exc:
        status("Apple Silicon MPS", False, f"torch check failed: {exc}")


def check_omlx() -> None:
    key = read_omlx_key()
    if not key:
        status("oMLX key", False, "not found in env or ~/.omlx/settings.json")
        return
    base_url = get_omlx_base_url()
    selected_model = get_omlx_model_name()
    request = urllib.request.Request(
        base_url.rstrip("/") + "/models",
        headers={"Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        models = payload.get("data", [])
        count = len(models)
        model_ids = {model.get("id") for model in models if isinstance(model, dict)}
        if selected_model in model_ids:
            status("oMLX API", True, f"{selected_model} available at {base_url} ({count} models)")
        else:
            available = ", ".join(sorted(model_id for model_id in model_ids if model_id)) or "none"
            status("oMLX API", False, f"configured model {selected_model} not found at {base_url}; available: {available}")
    except urllib.error.HTTPError as exc:
        status("oMLX API", False, f"HTTP {exc.code} at {base_url}")
    except Exception as exc:
        status("oMLX API", False, f"{exc}")


def check_data_index() -> None:
    index_status = read_index_status(data_dir=DATA_DIR, manifest_path=MANIFEST_PATH, root=ROOT)
    status("Dataset", index_status.downloaded_files == index_status.expected_files, f"{index_status.downloaded_files}/{index_status.expected_files} parquet files")
    status("Chroma index", bool(index_status.indexed_files), f"{index_status.indexed_files}/{index_status.expected_files} files, {index_status.in_progress_files} in progress, {index_status.indexed_chunks:,} chunks")


def disk_space_status(path: Path, min_free_gb: float) -> tuple[bool, str]:
    target = path if path.exists() else path.parent
    usage = shutil.disk_usage(target)
    free_gb = usage.free / (1024 ** 3)
    total_gb = usage.total / (1024 ** 3)
    return free_gb >= min_free_gb, f"{free_gb:.1f} GB free of {total_gb:.1f} GB at {target}"


def check_disk_space() -> None:
    min_free_gb = float(os.getenv("MIN_FREE_DISK_GB", "20"))
    ok, detail = disk_space_status(DB_DIR, min_free_gb)
    status("Disk space", ok, f"{detail}; minimum {min_free_gb:.1f} GB")


def check_retrieval() -> None:
    index_status = read_index_status(data_dir=DATA_DIR, manifest_path=MANIFEST_PATH, root=ROOT)
    if not index_status.complete:
        status("Retrieval", True, "skipped until full index is complete")
        return
    try:
        from rag_chain import get_vectorstore

        vectorstore = get_vectorstore()
        docs = vectorstore.as_retriever(search_kwargs={"k": 3}).invoke("Epstein aircraft")
        status("Retrieval", len(docs) >= 1, f"{len(docs)} docs returned")
    except Exception as exc:
        status("Retrieval", False, f"{exc}")


def check_ports() -> None:
    port = int(os.getenv("STREAMLIT_PORT", "8501"))
    with socket.socket() as sock:
        app_running = sock.connect_ex(("127.0.0.1", port)) == 0
    status("Streamlit app", True, f"running on {port}" if app_running else "not running")


def check_container_runtime() -> None:
    docker = command_exists("docker")
    status("Docker", docker, "installed" if docker else "not installed; compose files are present but not runnable locally")


if __name__ == "__main__":
    check_python()
    check_imports()
    check_mps()
    check_omlx()
    check_data_index()
    check_disk_space()
    check_retrieval()
    check_ports()
    check_container_runtime()
