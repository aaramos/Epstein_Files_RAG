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

        self.assertIn("read_index_status().complete", script)
        self.assertIn("run_capture final_audit scripts/final_audit.sh\n", script)
        self.assertIn("run_capture final_audit scripts/final_audit.sh --allow-incomplete --skip-app", script)


if __name__ == "__main__":
    unittest.main()
