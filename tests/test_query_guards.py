import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

from index_state import IndexStatus


ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QueryGuardTests(unittest.TestCase):
    def active_status(self):
        return IndexStatus(
            downloaded_files=634,
            expected_files=634,
            indexed_files=208,
            in_progress_files=1,
            indexed_docs=100,
            indexed_chunks=200,
            in_progress_names=("epstein_files-0208.parquet",),
        )

    def test_validate_refuses_active_index_by_default(self):
        validate_rag = load_script("validate_rag")
        with patch.object(validate_rag, "read_index_status", return_value=self.active_status()):
            with self.assertRaises(SystemExit) as raised:
                validate_rag.validate_safe_to_query(expected_files=634, allow_active_index=False)

        self.assertIn("Indexing is active", str(raised.exception))

    def test_validate_can_allow_active_index(self):
        validate_rag = load_script("validate_rag")
        with patch.object(validate_rag, "read_index_status", return_value=self.active_status()):
            validate_rag.validate_safe_to_query(expected_files=634, allow_active_index=True)

    def test_benchmark_refuses_active_index_by_default(self):
        benchmark = load_script("benchmark")
        with patch.object(benchmark, "read_index_status", return_value=self.active_status()):
            with self.assertRaises(SystemExit) as raised:
                benchmark.validate_safe_to_query(expected_files=634, allow_active_index=False)

        self.assertIn("Indexing is active", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
