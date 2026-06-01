import tempfile
import unittest
from pathlib import Path

from langchain_core.documents import Document

import faiss_store


class FakeEmbeddings:
    def embed_documents(self, texts):
        return [self._vector(text) for text in texts]

    def embed_query(self, text):
        return self._vector(text)

    def _vector(self, text):
        return [1.0, 0.0, 0.0, 0.0] if "aircraft" in text.lower() else [0.0, 1.0, 0.0, 0.0]


class FaissStoreTests(unittest.TestCase):
    def test_build_and_search_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            documents = [
                Document(
                    page_content="Epstein aircraft document",
                    metadata={"source": "a.parquet", "original_filename": "a.pdf", "row_number": 1},
                ),
                Document(
                    page_content="Unrelated finance document",
                    metadata={"source": "b.parquet", "original_filename": "b.pdf", "row_number": 2},
                ),
            ]
            payload = faiss_store.build_index([(documents, ["a:1", "b:2"])], FakeEmbeddings(), root=root)
            docs = faiss_store.search("aircraft", 1, FakeEmbeddings(), root=root)

        self.assertEqual(payload["chunks"], 2)
        self.assertTrue(payload["complete"])
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].metadata["retrieval_backend"], "faiss_hnsw")
        self.assertEqual(docs[0].page_content, "Epstein aircraft document")

    def test_available_requires_complete_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            faiss_store.metadata_path(root).write_text("")
            faiss_store.index_path(root).write_text("")
            faiss_store.manifest_path(root).write_text('{"chunks": 10, "complete": false}')

            self.assertFalse(faiss_store.available(root))

            faiss_store.manifest_path(root).write_text('{"chunks": 10, "complete": true}')
            self.assertTrue(faiss_store.available(root))


if __name__ == "__main__":
    unittest.main()
