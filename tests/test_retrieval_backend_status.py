import importlib.util
import os
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "retrieval_backend_status",
    ROOT / "scripts" / "retrieval_backend_status.py",
)
retrieval_backend_status = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(retrieval_backend_status)


class RetrievalBackendStatusTests(unittest.TestCase):
    def test_auto_prefers_faiss_when_available(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(retrieval_backend_status.faiss_store, "available", return_value=True):
                with patch.object(retrieval_backend_status.rag_chain, "_has_uncompacted_vector_wal", return_value=True):
                    payload = retrieval_backend_status.selected_backend()

        self.assertEqual(payload["selected"], "faiss_hnsw")
        self.assertIn("FAISS", payload["reason"])

    def test_auto_reports_sqlite_when_chroma_has_gap_and_faiss_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(retrieval_backend_status.faiss_store, "available", return_value=False):
                with patch.object(retrieval_backend_status.rag_chain, "_has_uncompacted_vector_wal", return_value=True):
                    payload = retrieval_backend_status.selected_backend()

        self.assertEqual(payload["selected"], "sqlite_fts")
        self.assertIn("Chroma", payload["reason"])

    def test_expect_rejects_wrong_backend(self):
        with patch.object(
            retrieval_backend_status,
            "selected_backend",
            return_value={
                "configured": "auto",
                "selected": "sqlite_fts",
                "reason": "gap",
                "faiss_available": False,
                "chroma_has_uncompacted_vector_wal": True,
            },
        ), patch("sys.argv", ["retrieval_backend_status.py", "--expect", "faiss_hnsw"]):
            with self.assertRaises(SystemExit) as context:
                retrieval_backend_status.main()

        self.assertIn("Expected backend faiss_hnsw", str(context.exception))

    def test_expect_accepts_matching_backend(self):
        with patch.object(
            retrieval_backend_status,
            "selected_backend",
            return_value={
                "configured": "auto",
                "selected": "faiss_hnsw",
                "reason": "complete",
                "faiss_available": True,
                "chroma_has_uncompacted_vector_wal": True,
            },
        ), patch("sys.argv", ["retrieval_backend_status.py", "--expect", "faiss_hnsw"]), patch(
            "sys.stdout", new_callable=StringIO
        ) as stdout:
            retrieval_backend_status.main()

        self.assertIn("Selected backend: faiss_hnsw", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
