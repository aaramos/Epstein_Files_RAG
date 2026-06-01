import os
import unittest
from unittest.mock import patch

import rag_chain


class RagChainTests(unittest.TestCase):
    def test_embedding_model_defaults_to_ingest_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(rag_chain.embedding_model(), "sentence-transformers/all-MiniLM-L6-v2")

    def test_embedding_model_reads_env(self):
        with patch.dict(os.environ, {"EMBEDDING_MODEL": "custom/model"}, clear=True):
            self.assertEqual(rag_chain.embedding_model(), "custom/model")

    def test_embedding_device_uses_cpu_when_auto_mps_unavailable(self):
        with patch.dict(os.environ, {"EMBEDDING_DEVICE": "auto"}, clear=True):
            with patch("torch.backends.mps.is_available", return_value=False):
                self.assertEqual(rag_chain._embedding_device(), "cpu")

    def test_embedding_device_respects_explicit_value(self):
        with patch.dict(os.environ, {"EMBEDDING_DEVICE": "cpu"}, clear=True):
            self.assertEqual(rag_chain._embedding_device(), "cpu")

    def test_retriever_falls_back_to_sqlite_fts(self):
        class FailingRetriever:
            def invoke(self, _query):
                raise RuntimeError("hnsw failed")

        class FakeVectorstore:
            def as_retriever(self, **_kwargs):
                return FailingRetriever()

        expected_docs = [object()]
        with patch.object(rag_chain, "get_vectorstore", return_value=FakeVectorstore()):
            with patch.object(rag_chain, "_sqlite_fts_search", return_value=expected_docs) as search:
                docs = rag_chain.get_retriever().invoke({"input": "Epstein aircraft"})

        self.assertEqual(docs, expected_docs)
        search.assert_called_once_with("Epstein aircraft", rag_chain.DEFAULT_RETRIEVER_K)

    def test_retriever_backend_can_force_sqlite_fts(self):
        with patch.dict(os.environ, {"RETRIEVER_BACKEND": "sqlite_fts"}, clear=True):
            with patch.object(rag_chain, "get_vectorstore") as vectorstore:
                with patch.object(rag_chain, "_sqlite_fts_search", return_value=[]) as search:
                    rag_chain.get_retriever().invoke({"input": "flight logs"})

        vectorstore.assert_not_called()
        search.assert_called_once_with("flight logs", rag_chain.DEFAULT_RETRIEVER_K)

    def test_retriever_auto_uses_sqlite_fts_for_uncompacted_wal(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(rag_chain, "get_vectorstore"):
                with patch.object(rag_chain, "_has_uncompacted_vector_wal", return_value=True):
                    with patch.object(rag_chain, "_sqlite_fts_search", return_value=[]) as search:
                        rag_chain.get_retriever().invoke({"input": "flight logs"})

        search.assert_called_once_with("flight logs", rag_chain.DEFAULT_RETRIEVER_K)


if __name__ == "__main__":
    unittest.main()
