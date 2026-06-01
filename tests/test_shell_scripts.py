import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ShellScriptTests(unittest.TestCase):
    def test_shell_scripts_parse(self):
        for script in sorted((ROOT / "scripts").glob("*.sh")):
            with self.subTest(script=script.name):
                result = subprocess.run(["bash", "-n", str(script)], text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_index_wrapper_forwards_stop_signals(self):
        script = (ROOT / "scripts" / "index_full_native.sh").read_text()

        self.assertIn("trap terminate_child TERM INT", script)
        self.assertIn("CHILD_PID=\"$!\"", script)
        self.assertIn("wait \"$CHILD_PID\"", script)

    def test_app_smoke_uses_dynamic_port_by_default(self):
        script = (ROOT / "scripts" / "smoke_app.sh").read_text()

        self.assertIn('if [[ -n "${STREAMLIT_PORT:-}" ]]', script)
        self.assertIn('sock.bind(("127.0.0.1", 0))', script)
        self.assertIn('STREAMLIT_PORT="$PORT"', script)

    def test_diagnostics_runs_full_audit_after_complete_index(self):
        script = (ROOT / "scripts" / "collect_diagnostics.sh").read_text()

        self.assertIn('FINAL_AUDIT_MODE="partial_skip_app"', script)
        self.assertIn('FINAL_AUDIT_MODE="full"', script)
        self.assertIn("final_audit_mode = sys.argv[3]", script)
        self.assertIn("read_index_status().complete", script)
        self.assertIn("run_capture final_audit scripts/final_audit.sh\n", script)
        self.assertIn("run_capture benchmark scripts/benchmark.sh", script)
        self.assertIn("run_raw_capture benchmark scripts/benchmark.sh --json", script)
        self.assertIn("run_capture final_audit scripts/final_audit.sh --allow-incomplete --skip-app", script)

    def test_diagnostics_manifest_summarizes_index_and_audit_state(self):
        script = (ROOT / "scripts" / "collect_diagnostics.sh").read_text()

        self.assertIn('progress = json_file("progress.json") or {}', script)
        self.assertIn('final_audit = json_file("final_audit.json") or {}', script)
        self.assertIn('"index_complete": progress.get("complete")', script)
        self.assertIn('"data_size_human": data.get("size_human")', script)
        self.assertIn('"index_size_human": index_storage.get("size_human")', script)
        self.assertIn('"index_free_human": index_storage.get("free_human")', script)
        self.assertIn('"projected_index_size_human": progress.get("projected_index_size_human")', script)
        self.assertIn('"eta_at_local": progress.get("eta_at_local")', script)
        self.assertIn('"final_audit_complete": final_audit.get("complete")', script)
        self.assertIn('"skipped_gates": final_audit.get("skipped_gates")', script)

    def test_wait_collects_diagnostics_after_validation_attempt(self):
        script = (ROOT / "scripts" / "wait_for_index.sh").read_text()

        self.assertIn("VALIDATION_STATUS=0", script)
        self.assertIn('scripts/final_audit.sh || VALIDATION_STATUS="$?"', script)
        self.assertIn("scripts/collect_diagnostics.sh", script)
        self.assertIn('exit "$VALIDATION_STATUS"', script)

    def test_wait_collects_diagnostics_after_stale_progress(self):
        script = (ROOT / "scripts" / "wait_for_index.sh").read_text()

        self.assertIn('PROGRESS_STATUS="$?"', script)
        self.assertIn('if [[ "$PROGRESS_STATUS" != "0" ]]', script)
        self.assertIn('exit "$PROGRESS_STATUS"', script)

    def test_wait_can_notify_macos_on_completion(self):
        script = (ROOT / "scripts" / "wait_for_index.sh").read_text()

        self.assertIn('MACOS_NOTIFY_ON_COMPLETE="${MACOS_NOTIFY_ON_COMPLETE:-0}"', script)
        self.assertIn("notify_macos()", script)
        self.assertIn("command -v osascript", script)
        self.assertIn('notify_macos "Epstein RAG index complete"', script)
        self.assertIn('notify_macos "Epstein RAG validation failed"', script)
        self.assertIn('notify_macos "Epstein RAG index stalled"', script)

    def test_check_runs_final_audit_after_complete_index(self):
        script = (ROOT / "scripts" / "check_all.sh").read_text()

        self.assertIn("Full index is not complete", script)
        self.assertIn("scripts/validate_rag.sh --min-docs 3", script)
        self.assertIn("scripts/benchmark.sh", script)
        self.assertIn("scripts/final_audit.sh", script)

    def test_makefile_exposes_mac_wait_helpers(self):
        makefile = (ROOT / "Makefile").read_text()

        self.assertIn("watch:", makefile)
        self.assertIn('scripts/progress.sh --watch $${INTERVAL_SECONDS:-60}', makefile)
        self.assertIn("wait-notify:", makefile)
        self.assertIn("MACOS_NOTIFY_ON_COMPLETE=1 scripts/wait_for_index.sh", makefile)

    def test_makefile_exposes_partial_audit(self):
        makefile = (ROOT / "Makefile").read_text()

        self.assertIn("partial-audit:", makefile)
        self.assertIn("scripts/final_audit.sh --allow-incomplete --skip-app", makefile)
        self.assertIn("partial-audit-json:", makefile)
        self.assertIn("scripts/final_audit.sh --allow-incomplete --skip-app --json", makefile)


if __name__ == "__main__":
    unittest.main()
