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

    def test_wait_collects_diagnostics_after_validation_attempt(self):
        script = (ROOT / "scripts" / "wait_for_index.sh").read_text()

        self.assertIn("VALIDATION_STATUS=0", script)
        self.assertIn('scripts/final_audit.sh || VALIDATION_STATUS="$?"', script)
        self.assertIn("scripts/collect_diagnostics.sh", script)
        self.assertIn('exit "$VALIDATION_STATUS"', script)

    def test_check_runs_final_audit_after_complete_index(self):
        script = (ROOT / "scripts" / "check_all.sh").read_text()

        self.assertIn("Full index is not complete", script)
        self.assertIn("scripts/validate_rag.sh --min-docs 3", script)
        self.assertIn("scripts/benchmark.sh", script)
        self.assertIn("scripts/final_audit.sh", script)


if __name__ == "__main__":
    unittest.main()
