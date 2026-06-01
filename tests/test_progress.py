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

    def test_payload_reports_stale_active_indexer(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "epstein_files-0000.parquet").touch()
            manifest_path = root / "manifest.json"
            log_path = root / "index.log"
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
                "INDEX_STALE_SECONDS": "60",
                "EXPECTED_PARQUET_FILES": "2",
            }

            with patch.dict(os.environ, env, clear=False):
                payload = progress.progress_payload()

        self.assertTrue(payload["indexing_active"])
        self.assertTrue(payload["stale"])
        self.assertEqual(payload["stale_seconds"], 60)
        self.assertEqual(payload["indexed_chunks"], 4)


if __name__ == "__main__":
    unittest.main()
