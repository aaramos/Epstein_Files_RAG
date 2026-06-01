import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("final_audit", ROOT / "scripts" / "final_audit.py")
final_audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(final_audit)


class FinalAuditTests(unittest.TestCase):
    def test_check_omlx_reports_missing_key(self):
        with patch.object(final_audit, "_get_omlx_api_key", return_value=None):
            ok, detail = final_audit.check_omlx()

        self.assertFalse(ok)
        self.assertIn("key not found", detail)

    def test_run_final_validation_builds_rag_command(self):
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="Validation OK\n",
            stderr="",
        )
        with patch.object(final_audit.subprocess, "run", return_value=completed) as run:
            ok, detail = final_audit.run_final_validation(skip_rag=False)

        self.assertTrue(ok)
        self.assertEqual(detail, "Validation OK")
        self.assertEqual(run.call_args.args[0], ["scripts/validate_rag.sh", "--require-full-index", "--rag"])

    def test_run_final_validation_can_skip_rag(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="Validation OK\n", stderr="")
        with patch.object(final_audit.subprocess, "run", return_value=completed) as run:
            ok, _ = final_audit.run_final_validation(skip_rag=True)

        self.assertTrue(ok)
        self.assertEqual(run.call_args.args[0], ["scripts/validate_rag.sh", "--require-full-index"])

    def test_run_app_smoke_returns_combined_failure_output(self):
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="app failed\n",
        )
        with patch.object(final_audit.subprocess, "run", return_value=completed):
            ok, detail = final_audit.run_app_smoke()

        self.assertFalse(ok)
        self.assertEqual(detail, "app failed")


if __name__ == "__main__":
    unittest.main()
