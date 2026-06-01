import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("doctor", ROOT / "scripts" / "doctor.py")
doctor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(doctor)


class DoctorTests(unittest.TestCase):
    def test_disk_space_status_accepts_sufficient_space(self):
        usage = Mock(total=100 * 1024**3, free=50 * 1024**3)
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(doctor.shutil, "disk_usage", return_value=usage):
                ok, detail = doctor.disk_space_status(Path(tmpdir), min_free_gb=20)

        self.assertTrue(ok)
        self.assertIn("50.0 GB free", detail)

    def test_disk_space_status_rejects_low_space(self):
        usage = Mock(total=100 * 1024**3, free=5 * 1024**3)
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(doctor.shutil, "disk_usage", return_value=usage):
                ok, detail = doctor.disk_space_status(Path(tmpdir), min_free_gb=20)

        self.assertFalse(ok)
        self.assertIn("5.0 GB free", detail)

    def test_check_mac_artifacts_reports_docker_and_launchd(self):
        with patch.object(doctor, "check_docker_assets", return_value=(True, "docker ok")), patch.object(
            doctor, "run_launchd_validation", return_value=(True, "launchd ok\nsecond line")
        ), patch.object(doctor, "status") as status:
            doctor.check_mac_artifacts()

        status.assert_any_call("Docker assets", True, "docker ok")
        status.assert_any_call("LaunchAgent templates", True, "launchd ok")


if __name__ == "__main__":
    unittest.main()
