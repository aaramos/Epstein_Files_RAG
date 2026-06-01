import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_chroma", ROOT / "scripts" / "validate_chroma.py")
validate_chroma = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_chroma)


class ValidateChromaTests(unittest.TestCase):
    def test_validate_diagnostics_accepts_caught_up_vector_segment(self):
        validate_chroma.validate_diagnostics(
            {
                "embeddings": 10,
                "vector_gap": 0,
                "vector_caught_up": True,
            }
        )

    def test_validate_diagnostics_rejects_vector_gap(self):
        with self.assertRaises(SystemExit) as context:
            validate_chroma.validate_diagnostics(
                {
                    "embeddings": 10,
                    "vector_gap": 2,
                    "vector_caught_up": False,
                }
            )

        self.assertIn("not caught up", str(context.exception))


if __name__ == "__main__":
    unittest.main()
