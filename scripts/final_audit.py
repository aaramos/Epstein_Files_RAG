from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from index_state import read_index_status
from llm_factory import _get_omlx_api_key


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit whether the Mac Studio RAG conversion is complete.")
    parser.add_argument("--allow-incomplete", action="store_true", help="Report incomplete gates without failing.")
    parser.add_argument("--skip-app", action="store_true", help="Skip Streamlit app launch smoke test.")
    parser.add_argument("--skip-rag", action="store_true", help="Skip final retrieval and oMLX generation validation.")
    return parser.parse_args()


def check_omlx() -> tuple[bool, str]:
    api_key = _get_omlx_api_key()
    if not api_key:
        return False, "oMLX API key not found"
    base_url = os.getenv("MORNING_DISPATCH_MODEL_BASE_URL") or os.getenv("OMLX_BASE_URL", "http://127.0.0.1:1234/v1")
    request = urllib.request.Request(
        base_url.rstrip("/") + "/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return False, f"oMLX models check failed at {base_url}: {exc}"
    return True, f"{len(payload.get('data', []))} models at {base_url}"


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


def main() -> None:
    args = parse_args()
    status = read_index_status(root=ROOT)
    gates: list[bool] = []

    data_ok = status.downloaded_files >= status.expected_files
    gates.append(data_ok)
    print_gate(data_ok, "Dataset", f"{status.downloaded_files}/{status.expected_files} parquet files")

    index_ok = status.complete
    gates.append(index_ok)
    print_gate(
        index_ok,
        "Full index",
        f"{status.indexed_files}/{status.expected_files} files, {status.in_progress_files} in progress, {status.indexed_chunks:,} chunks",
    )

    omlx_ok, omlx_detail = check_omlx()
    gates.append(omlx_ok)
    print_gate(omlx_ok, "oMLX", omlx_detail)

    if args.skip_app:
        print_gate(True, "Streamlit app", "skipped")
    else:
        app_ok, app_detail = run_app_smoke()
        gates.append(app_ok)
        print_gate(app_ok, "Streamlit app", app_detail.splitlines()[0])
        if not app_ok:
            print(app_detail)

    if index_ok:
        validation_ok, validation_detail = run_final_validation(args.skip_rag)
        gates.append(validation_ok)
        print_gate(validation_ok, "Final RAG validation", validation_detail.splitlines()[0])
        if not validation_ok:
            print(validation_detail)
    else:
        print_gate(False, "Final RAG validation", "skipped until full index is complete")
        gates.append(False)

    all_ok = all(gates)
    if all_ok:
        print("Final audit OK")
        return
    if args.allow_incomplete:
        print("Final audit incomplete; continuing is expected while indexing is still active.")
        return
    raise SystemExit("Final audit failed or is not complete yet")


if __name__ == "__main__":
    main()
