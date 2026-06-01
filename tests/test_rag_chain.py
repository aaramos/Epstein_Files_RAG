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


if __name__ == "__main__":
    unittest.main()
