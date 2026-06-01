import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from index_state import env_flag, query_enabled, read_index_status


class IndexStateTests(unittest.TestCase):
    def test_reads_manifest_and_download_counts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            data_dir = root / "data"
            data_dir.mkdir()
            for index in range(3):
                (data_dir / f"epstein_files-{index:04d}.parquet").touch()
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "completed_files": {
                            "epstein_files-0000.parquet": {"documents": 2, "chunks": 5},
                            "epstein_files-0001.parquet": {"documents": 3, "chunks": 7},
                        },
                        "in_progress": {"epstein_files-0002.parquet": {"started_at": "2026-01-01T00:00:00+00:00"}},
                    }
                )
            )

            status = read_index_status(data_dir=data_dir, manifest_path=manifest_path, expected_count=3)

        self.assertEqual(status.downloaded_files, 3)
        self.assertEqual(status.indexed_files, 2)
        self.assertEqual(status.in_progress_files, 1)
        self.assertEqual(status.indexed_docs, 5)
        self.assertEqual(status.indexed_chunks, 12)
        self.assertTrue(status.indexing_active)
        self.assertFalse(status.complete)

    def test_query_enabled_pauses_during_indexing_unless_allowed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            data_dir = root / "data"
            data_dir.mkdir()
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "completed_files": {"epstein_files-0000.parquet": {"documents": 1, "chunks": 1}},
                        "in_progress": {"epstein_files-0001.parquet": {}},
                    }
                )
            )
            status = read_index_status(data_dir=data_dir, manifest_path=manifest_path, expected_count=2)

        self.assertFalse(query_enabled(status))
        self.assertTrue(query_enabled(status, allow_during_index=True))

    def test_env_flag_parses_common_true_values(self):
        with patch.dict("os.environ", {"APP_ALLOW_QUERY_DURING_INDEX": "yes"}):
            self.assertTrue(env_flag("APP_ALLOW_QUERY_DURING_INDEX"))


if __name__ == "__main__":
    unittest.main()
