import os
import sqlite3
import tempfile
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

    def test_retriever_backend_can_force_faiss(self):
        expected_docs = [object()]
        fake_embeddings = object()
        with patch.dict(os.environ, {"RETRIEVER_BACKEND": "faiss"}, clear=True):
            with patch.object(rag_chain, "get_vectorstore") as vectorstore:
                with patch.object(rag_chain, "get_embeddings", return_value=fake_embeddings):
                    with patch.object(rag_chain.faiss_store, "search", return_value=expected_docs) as search:
                        docs = rag_chain.get_retriever().invoke({"input": "flight logs"})

        self.assertEqual(docs, expected_docs)
        vectorstore.assert_not_called()
        search.assert_called_once_with("flight logs", rag_chain.DEFAULT_RETRIEVER_K, fake_embeddings)

    def test_retriever_auto_uses_sqlite_fts_for_uncompacted_wal(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(rag_chain, "get_vectorstore"):
                with patch.object(rag_chain, "_has_uncompacted_vector_wal", return_value=True):
                    with patch.object(rag_chain, "_sqlite_fts_search", return_value=[]) as search:
                        rag_chain.get_retriever().invoke({"input": "flight logs"})

        search.assert_called_once_with("flight logs", rag_chain.DEFAULT_RETRIEVER_K)

    def test_sqlite_fts_search_joins_hits_by_embedding_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "chroma.sqlite3")
            with sqlite3.connect(db_path) as connection:
                connection.executescript(
                    """
                    CREATE VIRTUAL TABLE embedding_fulltext_search USING fts5(string_value, tokenize='trigram');
                    CREATE TABLE embedding_metadata (
                        id INTEGER,
                        key TEXT NOT NULL,
                        string_value TEXT,
                        int_value INTEGER,
                        float_value REAL,
                        bool_value INTEGER,
                        PRIMARY KEY (id, key)
                    );
                    INSERT INTO embedding_fulltext_search(rowid, string_value)
                    VALUES (42, 'Epstein Boeing aircraft evidence');
                    INSERT INTO embedding_metadata(id, key, string_value)
                    VALUES (99, 'chroma:document', 'wrong rowid document');
                    INSERT INTO embedding_metadata(id, key, string_value)
                    VALUES (42, 'chroma:document', 'right embedding document');
                    INSERT INTO embedding_metadata(id, key, string_value)
                    VALUES (42, 'source', 'epstein_files-test.parquet');
                    INSERT INTO embedding_metadata(id, key, string_value)
                    VALUES (42, 'original_filename', 'source.pdf');
                    INSERT INTO embedding_metadata(id, key, int_value)
                    VALUES (42, 'row_number', 7);
                    """
                )

            with patch.object(rag_chain, "DB_DIR", tmpdir):
                docs = rag_chain._sqlite_fts_search("Epstein aircraft", 3)

        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].page_content, "right embedding document")
        self.assertEqual(docs[0].metadata["source"], "epstein_files-test.parquet")
        self.assertEqual(docs[0].metadata["row_number"], 7)

    def test_fts_terms_keeps_epstein_as_query_anchor(self):
        self.assertEqual(rag_chain._fts_terms("What aircraft did Epstein use?"), ["aircraft", "epstein", "use"])


if __name__ == "__main__":
    unittest.main()
