from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from index_state import read_index_status
from llm_factory import _get_omlx_api_key, get_omlx_base_url, get_omlx_model_name


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


def print_gate(ok: bool, label: str, detail: str) -> None:
    marker = "OK" if ok else "WAIT"
    print(f"[{marker}] {label}: {detail}")


def add_gate(gates: list[dict], key: str, label: str, ok: bool, detail: str, skipped: bool = False) -> None:
    gates.append({"key": key, "label": label, "ok": ok, "detail": detail, "skipped": skipped})


def audit_payload(skip_app: bool = False, skip_rag: bool = False) -> dict:
    status = read_index_status(root=ROOT)
    gates: list[dict] = []

    data_ok = status.downloaded_files >= status.expected_files
    add_gate(gates, "dataset", "Dataset", data_ok, f"{status.downloaded_files}/{status.expected_files} parquet files")

    index_ok = status.complete
    add_gate(gates, "full_index", "Full index", index_ok, f"{status.indexed_files}/{status.expected_files} files, {status.in_progress_files} in progress, {status.indexed_chunks:,} chunks")

    omlx_ok, omlx_detail = check_omlx()
    add_gate(gates, "omlx", "oMLX", omlx_ok, omlx_detail)

    if skip_app:
        add_gate(gates, "streamlit_app", "Streamlit app", True, "skipped", skipped=True)
    else:
        app_ok, app_detail = run_app_smoke()
        add_gate(gates, "streamlit_app", "Streamlit app", app_ok, app_detail)

    if index_ok:
        validation_ok, validation_detail = run_final_validation(skip_rag)
        add_gate(gates, "final_rag_validation", "Final RAG validation", validation_ok, validation_detail)
    else:
        add_gate(gates, "final_rag_validation", "Final RAG validation", False, "skipped until full index is complete", skipped=True)

    actionable_gates = [gate for gate in gates if not gate["skipped"]]
    all_ok = all(gate["ok"] for gate in gates)
    complete = all_ok and bool(actionable_gates)
    return {
        "complete": complete,
        "gates": gates,
        "index": {
            "downloaded_files": status.downloaded_files,
            "expected_files": status.expected_files,
            "indexed_files": status.indexed_files,
            "in_progress_files": status.in_progress_files,
            "indexed_chunks": status.indexed_chunks,
        },
    }


def print_human(payload: dict) -> None:
    for gate in payload["gates"]:
        print_gate(gate["ok"], gate["label"], gate["detail"].splitlines()[0])
        if not gate["ok"] and "\n" in gate["detail"]:
            print(gate["detail"])


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
