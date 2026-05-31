import tempfile
import unittest
from pathlib import Path

import pandas as pd

import ingest


class IngestTests(unittest.TestCase):
    def make_parquet(self, rows):
        tmpdir = tempfile.TemporaryDirectory()
        path = Path(tmpdir.name) / "epstein_files-9999.parquet"
        pd.DataFrame(rows).to_parquet(path)
        self.addCleanup(tmpdir.cleanup)
        return path

    def test_available_columns_prefers_text_content(self):
        path = self.make_parquet(
            [
                {
                    "text_content": "This is a long enough document body for testing.",
                    "text": "secondary",
                    "file_name": "source.pdf",
                    "unused": "skip me",
                }
            ]
        )

        text_col, columns = ingest.available_columns(path)

        self.assertEqual(text_col, "text_content")
        self.assertIn("file_name", columns)
        self.assertNotIn("unused", columns)

    def test_iter_document_batches_streams_rows_with_metadata(self):
        path = self.make_parquet(
            [
                {"text_content": "short", "file_name": "skip.pdf"},
                {
                    "text_content": "This document has enough text to survive the minimum length filter.",
                    "file_name": "doc-a.pdf",
                },
                {
                    "text_content": "This second document also has enough text to be yielded properly.",
                    "file_name": "doc-b.pdf",
                },
            ]
        )

        batches = list(ingest.iter_document_batches(path, row_batch_size=2))
        documents = [doc for batch in batches for doc in batch]

        self.assertEqual(len(documents), 2)
        self.assertEqual(documents[0].metadata["row_number"], 2)
        self.assertEqual(documents[0].metadata["original_filename"], "doc-a.pdf")
        self.assertEqual(documents[1].metadata["row_number"], 3)

    def test_chunks_have_stable_source_row_ids(self):
        path = self.make_parquet(
            [
                {
                    "text_content": "This document has enough text to become one stable indexed chunk.",
                    "file_name": "doc-a.pdf",
                }
            ]
        )
        documents = list(ingest.iter_document_batches(path))[0]

        chunks_a, ids_a = ingest.chunks_with_ids(documents)
        chunks_b, ids_b = ingest.chunks_with_ids(documents)

        self.assertEqual(ids_a, ids_b)
        self.assertEqual(len(ids_a), len(chunks_a))
        self.assertTrue(ids_a[0].startswith("epstein_files-9999.parquet:1:0:"))


if __name__ == "__main__":
    unittest.main()
