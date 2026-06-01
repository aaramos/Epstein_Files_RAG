from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from index_state import read_index_status
from index_lock import process_alive, read_lock, release_stale_lock
from llm_factory import _get_omlx_api_key, get_omlx_base_url, get_omlx_model_name
from faiss_progress import payload as faiss_progress_payload
from progress import human_duration, progress_payload, stale_failure_reason
from validate_chroma import validate_diagnostics, validate_reader
from chroma_vector_diagnostics import inspect_chroma


DB_DIR = Path(os.getenv("DB_PATH", str(ROOT / "chroma_db")))
FAISS_DIR = Path(os.getenv("FAISS_INDEX_DIR", str(ROOT / "faiss_index")))
SAMPLE_LIMIT = 5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit whether the Mac Studio RAG conversion is complete.")
    parser.add_argument("--allow-incomplete", action="store_true", help="Report incomplete gates without failing.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--skip-app", action="store_true", help="Skip Streamlit app launch smoke test.")
    parser.add_argument("--skip-rag", action="store_true", help="Skip final retrieval and oMLX generation validation.")
    return parser.parse_args()


def check_omlx() -> tuple[bool, str]:
    api_key = _get_omlx_api_key()
    if not api_key:
        return False, "oMLX API key not found"
    base_url = get_omlx_base_url()
    selected_model = get_omlx_model_name()
    request = urllib.request.Request(
        base_url.rstrip("/") + "/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return False, f"oMLX models check failed at {base_url}: {exc}"
    models = payload.get("data", [])
    model_ids = {model.get("id") for model in models if isinstance(model, dict)}
    if selected_model not in model_ids:
        available = ", ".join(sorted(model_id for model_id in model_ids if model_id)) or "none"
        return False, f"configured model {selected_model} not found at {base_url}; available: {available}"
    return True, f"{selected_model} available at {base_url} ({len(models)} models)"


def run_final_validation(skip_rag: bool) -> tuple[bool, str]:
    command = ["scripts/validate_rag.sh", "--require-full-index"]
    if not skip_rag:
        command.append("--rag")
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    return result.returncode == 0, output or "validation produced no output"


def run_app_smoke() -> tuple[bool, str]:
    result = subprocess.run(["scripts/smoke_app.sh"], cwd=ROOT, text=True, capture_output=True)
    output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    return result.returncode == 0, output or "app smoke produced no output"


def run_launchd_validation() -> tuple[bool, str]:
    result = subprocess.run(["scripts/launchd_manage.sh", "validate"], cwd=ROOT, text=True, capture_output=True)
    output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    return result.returncode == 0, output or "LaunchAgent validation produced no output"


def check_docker_assets() -> tuple[bool, str]:
    dockerfile = ROOT / "Dockerfile"
    compose = ROOT / "docker-compose.yml"
    dockerignore = ROOT / ".dockerignore"
    missing = [path.name for path in (dockerfile, compose, dockerignore) if not path.exists()]
    if missing:
        return False, "missing " + ", ".join(missing)

    dockerfile_text = dockerfile.read_text()
    compose_text = compose.read_text()
    dockerignore_lines = set(dockerignore.read_text().splitlines())
    checks = {
        "Dockerfile exposes Streamlit": "EXPOSE 8501" in dockerfile_text,
        "Dockerfile has healthcheck": "HEALTHCHECK" in dockerfile_text,
        "Dockerfile runs Streamlit on 0.0.0.0": "--server.address" in dockerfile_text and "0.0.0.0" in dockerfile_text,
        "Compose routes oMLX to host": "host.docker.internal:1234/v1" in compose_text,
        "Compose mounts data": "./data:/app/data" in compose_text,
        "Compose mounts Chroma": "./chroma_db:/app/chroma_db" in compose_text,
        "Compose includes healthcheck": "healthcheck:" in compose_text,
        "Dockerignore excludes data": "data" in dockerignore_lines,
        "Dockerignore excludes Chroma": "chroma_db" in dockerignore_lines,
    }
    failed = [label for label, ok in checks.items() if not ok]
    if failed:
        return False, "; ".join(failed)
    return True, "Dockerfile, compose, healthcheck, oMLX host routing, and large-data ignores are present"


def index_lock_path() -> Path:
    return Path(os.getenv("INDEX_LOCK_PATH", str(ROOT / "runtime" / "index_full.lock")))


def check_index_lock(indexing_active: bool) -> tuple[bool, str]:
    path = index_lock_path()
    lock = read_lock(path)
    if not isinstance(lock, dict):
        if indexing_active:
            return False, f"indexing is active but no lock exists at {path}"
        return True, "no active index lock"

    pid = lock.get("pid")
    if not isinstance(pid, int):
        return False, f"index lock at {path} does not contain a valid PID"
    if process_alive(pid):
        return True, f"lock owned by live PID {pid}"
    return False, f"stale index lock at {path} for PID {pid}"


def clean_stale_index_lock() -> bool:
    return release_stale_lock(index_lock_path())


def check_index_progress(indexing_active: bool) -> tuple[bool, str]:
    if not indexing_active:
        return True, "no active indexer"

    payload = progress_payload()
    reason = stale_failure_reason(payload)
    if reason:
        return False, reason

    manifest_age = human_duration(payload.get("manifest_age_seconds"))
    log_age = human_duration(payload.get("index_log_age_seconds"))
    return True, f"active indexer fresh; manifest updated {manifest_age} ago, index log updated {log_age} ago"


def check_disk_space() -> tuple[bool, str]:
    min_free_gb = float(os.getenv("MIN_FREE_DISK_GB", "20"))
    target = DB_DIR if DB_DIR.exists() else DB_DIR.parent
    usage = shutil.disk_usage(target)
    free_gb = usage.free / (1024 ** 3)
    total_gb = usage.total / (1024 ** 3)
    ok = free_gb >= min_free_gb
    return ok, f"{free_gb:.1f} GB free of {total_gb:.1f} GB at {target}; minimum {min_free_gb:.1f} GB"


def check_faiss_backend() -> tuple[bool, str]:
    data = faiss_progress_payload(FAISS_DIR, ROOT / "chroma_db" / "ingest_manifest.json")
    chunks = int(data.get("chunks") or 0)
    expected = data.get("expected_chunks")
    if data.get("complete") is not True:
        if expected:
            return False, f"FAISS incomplete: {chunks:,}/{expected:,} chunks ({chunks / expected:.1%})"
        return False, f"FAISS incomplete: {chunks:,} chunks"
    if expected and chunks != expected:
        return False, f"FAISS complete marker present but chunk count is {chunks:,}/{expected:,}"
    metadata_chunks = data.get("metadata_chunks")
    if metadata_chunks is not None and int(metadata_chunks) != chunks:
        return False, f"FAISS metadata rows {int(metadata_chunks):,} do not match manifest chunks {chunks:,}"
    return True, f"FAISS complete with {chunks:,} chunks"


def check_chroma_backend() -> tuple[bool, str]:
    try:
        data = inspect_chroma(DB_DIR)
        validate_diagnostics(data)
        validate_reader(DB_DIR, int(data["embeddings"]))
    except SystemExit as exc:
        detail = str(exc) or "Chroma validation failed"
        return False, detail
    except Exception as exc:
        return False, f"Chroma reader failed: {exc}"
    return True, f"Chroma HNSW readable with {int(data['embeddings']):,} vectors"


def print_gate(ok: bool, label: str, detail: str) -> None:
    marker = "OK" if ok else "WAIT"
    print(f"[{marker}] {label}: {detail}")


def add_gate(gates: list[dict], key: str, label: str, ok: bool, detail: str, skipped: bool = False) -> None:
    gates.append({"key": key, "label": label, "ok": ok, "detail": detail, "skipped": skipped})


def full_index_detail(status) -> str:
    detail = f"{status.indexed_files}/{status.expected_files} files, {status.in_progress_files} in progress, {status.indexed_chunks:,} chunks"
    if status.missing_indexed_names:
        detail += f", {len(status.missing_indexed_names)} downloaded files not indexed"
    if status.unexpected_indexed_names:
        detail += f", {len(status.unexpected_indexed_names)} manifest entries missing from data"
    return detail


def audit_payload(skip_app: bool = False, skip_rag: bool = False) -> dict:
    clean_stale_index_lock()
    status = read_index_status(root=ROOT)
    progress = progress_payload() if status.indexing_active else None
    gates: list[dict] = []

    data_ok = status.downloaded_files >= status.expected_files
    add_gate(gates, "dataset", "Dataset", data_ok, f"{status.downloaded_files}/{status.expected_files} parquet files")

    index_ok = status.complete
    add_gate(gates, "full_index", "Full index", index_ok, full_index_detail(status))

    lock_ok, lock_detail = check_index_lock(status.indexing_active)
    add_gate(gates, "index_lock", "Index lock", lock_ok, lock_detail)

    progress_ok, progress_detail = check_index_progress(status.indexing_active)
    add_gate(gates, "index_progress", "Index progress", progress_ok, progress_detail)

    disk_ok, disk_detail = check_disk_space()
    add_gate(gates, "disk_space", "Disk space", disk_ok, disk_detail)

    chroma_ok, chroma_detail = check_chroma_backend()
    add_gate(gates, "chroma_backend", "Chroma backend", chroma_ok, chroma_detail)

    faiss_ok, faiss_detail = check_faiss_backend()
    add_gate(gates, "faiss_backend", "FAISS backend", faiss_ok, faiss_detail)

    omlx_ok, omlx_detail = check_omlx()
    add_gate(gates, "omlx", "oMLX", omlx_ok, omlx_detail)

    docker_ok, docker_detail = check_docker_assets()
    add_gate(gates, "docker_assets", "Docker assets", docker_ok, docker_detail)

    launchd_ok, launchd_detail = run_launchd_validation()
    add_gate(gates, "launchd_templates", "LaunchAgent templates", launchd_ok, launchd_detail)

    if skip_app:
        add_gate(gates, "streamlit_app", "Streamlit app", True, "skipped", skipped=True)
    else:
        app_ok, app_detail = run_app_smoke()
        add_gate(gates, "streamlit_app", "Streamlit app", app_ok, app_detail)

    if index_ok:
        validation_ok, validation_detail = run_final_validation(skip_rag)
        add_gate(gates, "final_rag_validation", "Final RAG validation", validation_ok, validation_detail)
        if skip_rag:
            add_gate(gates, "rag_generation", "RAG generation", True, "skipped", skipped=True)
    else:
        add_gate(gates, "final_rag_validation", "Final RAG validation", False, "skipped until full index is complete", skipped=True)

    skipped_gates = [gate for gate in gates if gate["skipped"]]
    all_ok = all(gate["ok"] for gate in gates)
    complete = all_ok and not skipped_gates
    payload = {
        "complete": complete,
        "gates": gates,
        "skipped_gates": [gate["key"] for gate in skipped_gates],
        "index": {
            "downloaded_files": status.downloaded_files,
            "expected_files": status.expected_files,
            "indexed_files": status.indexed_files,
            "indexed_fraction": status.indexed_files / status.expected_files if status.expected_files else None,
            "in_progress_files": status.in_progress_files,
            "indexed_chunks": status.indexed_chunks,
            "missing_indexed_files": len(status.missing_indexed_names),
            "missing_indexed_sample": list(status.missing_indexed_names[:SAMPLE_LIMIT]),
            "unexpected_indexed_files": len(status.unexpected_indexed_names),
            "unexpected_indexed_sample": list(status.unexpected_indexed_names[:SAMPLE_LIMIT]),
        },
    }
    if progress:
        payload["progress"] = {
            "data": progress.get("data"),
            "index_storage": progress.get("index_storage"),
            "rate_files_per_minute": progress.get("rate_files_per_minute"),
            "eta_seconds": progress.get("eta_seconds"),
            "eta_at_utc": progress.get("eta_at_utc"),
            "eta_at_local": progress.get("eta_at_local"),
            "projected_index_size_human": progress.get("projected_index_size_human"),
            "manifest_age_seconds": progress.get("manifest_age_seconds"),
            "index_log_age_seconds": progress.get("index_log_age_seconds"),
        }
    return payload


def print_human(payload: dict) -> None:
    for gate in payload["gates"]:
        print_gate(gate["ok"], gate["label"], gate["detail"].splitlines()[0])
        if not gate["ok"] and "\n" in gate["detail"]:
            print(gate["detail"])
    progress = payload.get("progress")
    if progress:
        rate = progress.get("rate_files_per_minute")
        eta = human_duration(progress.get("eta_seconds"))
        eta_local = progress.get("eta_at_local")
        if rate:
            print(f"[INFO] Index rate: {rate:.2f} files/min")
        print(f"[INFO] Index ETA: {eta}")
        if eta_local:
            print(f"[INFO] Estimated completion local: {eta_local}")


def main() -> None:
    args = parse_args()
    payload = audit_payload(skip_app=args.skip_app, skip_rag=args.skip_rag)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_human(payload)

    if payload["complete"]:
        if not args.json:
            print("Final audit OK")
        return
    if args.allow_incomplete:
        if not args.json:
            print("Final audit incomplete; continuing is expected while indexing is still active.")
        return
    raise SystemExit("Final audit failed or is not complete yet")


if __name__ == "__main__":
    main()
