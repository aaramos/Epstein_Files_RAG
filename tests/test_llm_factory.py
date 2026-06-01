import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import llm_factory


class LlmFactoryTests(unittest.TestCase):
    def test_omlx_key_prefers_morning_dispatch_env(self):
        env = {
            "MORNING_DISPATCH_MODEL_API_KEY": "morning-key",
            "OMLX_API_KEY": "omlx-key",
        }
        with patch.dict(os.environ, env, clear=False):
            self.assertEqual(llm_factory._get_omlx_api_key(), "morning-key")

    def test_omlx_key_reads_settings_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"
            settings_path.write_text('{"auth": {"api_key": "settings-key"}}')
            env = {
                "OMLX_SETTINGS_PATH": str(settings_path),
                "MORNING_DISPATCH_MODEL_API_KEY": "",
                "OMLX_API_KEY": "",
                "LM_API_KEY": "",
                "ANTHROPIC_AUTH_TOKEN": "",
            }
            with patch.dict(os.environ, env, clear=False):
                self.assertEqual(llm_factory._get_omlx_api_key(), "settings-key")

    def test_get_llm_defaults_to_omlx_provider(self):
        env = {"OMLX_API_KEY": "test-key"}
        with patch.dict(os.environ, env, clear=True):
            with patch.object(llm_factory, "ChatOpenAI") as chat_openai:
                llm_factory.get_llm()

        self.assertTrue(chat_openai.called)
        self.assertEqual(chat_openai.call_args.kwargs["model_name"], "Gemma4-MTP-26B-BF16")


if __name__ == "__main__":
    unittest.main()
