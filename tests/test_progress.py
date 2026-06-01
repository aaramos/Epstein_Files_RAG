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
    def test_human_size_formats_common_ranges(self):
        self.assertEqual(progress.human_size(None), "unknown")
        self.assertEqual(progress.human_size(7), "7 B")
        self.assertEqual(progress.human_size(2048), "2.0 KB")
        self.assertEqual(progress.human_size(3 * 1024**3), "3.0 GB")

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
            (data_dir / "epstein_files-0001.parquet").touch()
            (data_dir / "epstein_files-0000.parquet").write_bytes(b"abcd")
            (data_dir / "epstein_files-0001.parquet").write_bytes(b"ef")
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
        self.assertEqual(payload["data"]["size_bytes"], 6)
        self.assertEqual(payload["data"]["size_human"], "6 B")
        self.assertTrue(payload["stale"])
        self.assertEqual(payload["stale_seconds"], 60)
        self.assertEqual(payload["indexed_chunks"], 4)
        self.assertEqual(payload["missing_indexed_files"], 1)
        self.assertEqual(payload["missing_indexed_sample"], ["epstein_files-0001.parquet"])
        self.assertEqual(payload["unexpected_indexed_sample"], [])
        self.assertIsNotNone(payload["eta_at_utc"])
        self.assertIsNotNone(payload["eta_at_local"])
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

    def test_watch_count_requires_watch(self):
        with patch.object(progress.sys, "argv", ["progress.py", "--watch-count", "1"]):
            with self.assertRaises(SystemExit) as raised:
                progress.main()

        self.assertIn("--watch-count requires --watch", str(raised.exception))

    def test_watch_mode_stops_after_count(self):
        payload = {
            "complete": False,
            "stale": False,
            "indexer_process_missing": False,
            "indexing_active": True,
            "index_lock": {"present": True, "stale": False},
        }

        with patch.object(progress.sys, "argv", ["progress.py", "--watch", "1", "--watch-count", "2"]):
            with patch.object(progress, "progress_payload", return_value=payload) as payload_mock:
                with patch.object(progress, "print_human") as print_mock:
                    with patch.object(progress.time, "sleep") as sleep_mock:
                        progress.main()

        self.assertEqual(payload_mock.call_count, 2)
        self.assertEqual(print_mock.call_count, 2)
        sleep_mock.assert_called_once_with(1.0)

    def test_data_payload_reports_symlink_resolution(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            real_data = root / "real-data"
            real_data.mkdir()
            (real_data / "epstein_files-0000.parquet").write_bytes(b"abcd")
            linked_data = root / "data"
            linked_data.symlink_to(real_data)

            with patch.dict(os.environ, {"DATA_PATH": str(linked_data)}, clear=False):
                payload = progress.data_payload(root)

        self.assertTrue(payload["is_symlink"])
        self.assertEqual(payload["path"], str(linked_data))
        self.assertEqual(payload["resolved_path"], str(real_data.resolve()))
        self.assertEqual(payload["size_bytes"], 4)

    def test_index_storage_payload_reports_chroma_size(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_dir = root / "chroma_db"
            db_dir.mkdir()
            (db_dir / "index.sqlite3").write_bytes(b"abc")
            subdir = db_dir / "segments"
            subdir.mkdir()
            (subdir / "segment.bin").write_bytes(b"de")

            with patch.dict(os.environ, {"DB_PATH": str(db_dir)}, clear=False):
                payload = progress.index_storage_payload(root)

        self.assertEqual(payload["path"], str(db_dir))
        self.assertEqual(payload["size_bytes"], 5)
        self.assertEqual(payload["size_human"], "5 B")


if __name__ == "__main__":
    unittest.main()
