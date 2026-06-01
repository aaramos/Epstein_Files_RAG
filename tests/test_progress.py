import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("progress", ROOT / "scripts" / "progress.py")
progress = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(progress)


class ProgressTests(unittest.TestCase):
    def test_human_duration_formats_common_ranges(self):
        self.assertEqual(progress.human_duration(None), "unknown")
        self.assertEqual(progress.human_duration(7), "7s")
        self.assertEqual(progress.human_duration(67), "1m 7s")
        self.assertEqual(progress.human_duration(3661), "1h 1m")

    def test_parse_process_lines(self):
        processes = progress.parse_process_lines(
            [
                "88198 /opt/homebrew/bin/python ingest.py --all",
                "not-a-pid python ingest.py",
                "",
            ]
        )

        self.assertEqual(processes, [{"pid": 88198, "command": "/opt/homebrew/bin/python ingest.py --all"}])

    def test_payload_reports_stale_active_indexer(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "epstein_files-0000.parquet").touch()
            manifest_path = root / "manifest.json"
            log_path = root / "index.log"
            lock_path = root / "index.lock"
            lock_path.write_text(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "command": "python ingest.py",
                        "created_at": "2026-01-01T00:00:00+00:00",
                    }
                )
            )
            manifest_path.write_text(
                json.dumps(
                    {
                        "completed_files": {
                            "epstein_files-0000.parquet": {
                                "documents": 2,
                                "chunks": 4,
                                "indexed_at": "2026-01-01T00:00:00+00:00",
                            }
                        },
                        "in_progress": {"epstein_files-0001.parquet": {"started_at": "2026-01-01T00:01:00+00:00"}},
                    }
                )
            )
            log_path.write_text("quiet\n")
            old_timestamp = time.time() - 120
            os.utime(log_path, (old_timestamp, old_timestamp))
            env = {
                "DATA_PATH": str(data_dir),
                "INGEST_MANIFEST_PATH": str(manifest_path),
                "INDEX_LOG_PATH": str(log_path),
                "INDEX_LOCK_PATH": str(lock_path),
                "INDEX_STALE_SECONDS": "60",
                "EXPECTED_PARQUET_FILES": "2",
            }

            with patch.dict(os.environ, env, clear=False):
                with patch.object(progress, "scan_indexer_processes", return_value=([{"pid": 123, "command": "python ingest.py"}], True)):
                    payload = progress.progress_payload()

        self.assertTrue(payload["indexing_active"])
        self.assertTrue(payload["stale"])
        self.assertEqual(payload["stale_seconds"], 60)
        self.assertEqual(payload["indexed_chunks"], 4)
        self.assertEqual(payload["indexer_process_count"], 1)
        self.assertFalse(payload["indexer_process_missing"])
        self.assertTrue(payload["indexer_process_scan_available"])
        self.assertTrue(payload["index_lock"]["present"])
        self.assertEqual(payload["index_lock"]["pid"], os.getpid())
        self.assertTrue(payload["index_lock"]["pid_alive"])

    def test_payload_reports_missing_indexer_process(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            data_dir = root / "data"
            data_dir.mkdir()
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "completed_files": {},
                        "in_progress": {"epstein_files-0001.parquet": {"started_at": "2026-01-01T00:01:00+00:00"}},
                    }
                )
            )
            env = {
                "DATA_PATH": str(data_dir),
                "INGEST_MANIFEST_PATH": str(manifest_path),
                "INDEX_LOG_PATH": str(root / "missing.log"),
                "EXPECTED_PARQUET_FILES": "2",
            }

            with patch.dict(os.environ, env, clear=False):
                with patch.object(progress, "scan_indexer_processes", return_value=([], True)):
                    payload = progress.progress_payload()

        self.assertTrue(payload["indexing_active"])
        self.assertEqual(payload["indexer_process_count"], 0)
        self.assertTrue(payload["indexer_process_missing"])

    def test_payload_does_not_warn_when_process_scan_unavailable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            data_dir = root / "data"
            data_dir.mkdir()
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "completed_files": {},
                        "in_progress": {"epstein_files-0001.parquet": {"started_at": "2026-01-01T00:01:00+00:00"}},
                    }
                )
            )
            env = {
                "DATA_PATH": str(data_dir),
                "INGEST_MANIFEST_PATH": str(manifest_path),
                "INDEX_LOG_PATH": str(root / "missing.log"),
                "EXPECTED_PARQUET_FILES": "2",
            }

            with patch.dict(os.environ, env, clear=False):
                with patch.object(progress, "scan_indexer_processes", return_value=([], False)):
                    payload = progress.progress_payload()

        self.assertFalse(payload["indexer_process_scan_available"])
        self.assertFalse(payload["indexer_process_missing"])

    def test_lock_payload_reports_missing_lock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {"INDEX_LOCK_PATH": str(Path(tmpdir) / "missing.lock")}
            with patch.dict(os.environ, env, clear=False):
                payload = progress.lock_payload(progress.datetime.now(progress.timezone.utc))

        self.assertFalse(payload["present"])
        self.assertFalse(payload["pid_alive"])

    def test_lock_payload_reports_stale_lock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "index.lock"
            lock_path.write_text(
                json.dumps(
                    {
                        "pid": 999999999,
                        "command": "old index",
                        "created_at": "2026-01-01T00:00:00+00:00",
                    }
                )
            )
            env = {"INDEX_LOCK_PATH": str(lock_path)}
            with patch.dict(os.environ, env, clear=False):
                payload = progress.lock_payload(progress.datetime.now(progress.timezone.utc))

        self.assertTrue(payload["present"])
        self.assertFalse(payload["pid_alive"])
        self.assertTrue(payload["stale"])

    def test_stale_failure_reason_reports_quiet_log_first(self):
        payload = {
            "stale": True,
            "stale_seconds": 60,
            "indexer_process_missing": True,
            "indexing_active": True,
            "index_lock": {"present": True, "stale": False},
        }

        self.assertIn("quiet", progress.stale_failure_reason(payload))

    def test_stale_failure_reason_reports_missing_lock(self):
        payload = {
            "stale": False,
            "stale_seconds": 60,
            "indexer_process_missing": False,
            "indexing_active": True,
            "index_lock": {"present": False, "stale": False},
        }

        self.assertIn("no index lock", progress.stale_failure_reason(payload))

    def test_stale_failure_reason_allows_healthy_payload(self):
        payload = {
            "stale": False,
            "stale_seconds": 60,
            "indexer_process_missing": False,
            "indexing_active": True,
            "index_lock": {"present": True, "stale": False},
        }

        self.assertIsNone(progress.stale_failure_reason(payload))


if __name__ == "__main__":
    unittest.main()
