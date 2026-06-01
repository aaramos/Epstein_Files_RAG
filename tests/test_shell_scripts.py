import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ShellScriptTests(unittest.TestCase):
    def test_shell_scripts_parse(self):
        for script in sorted((ROOT / "scripts").glob("*.sh")):
            with self.subTest(script=script.name):
                result = subprocess.run(["bash", "-n", str(script)], text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_index_wrapper_forwards_stop_signals(self):
        script = (ROOT / "scripts" / "index_full_native.sh").read_text()

        self.assertIn("trap terminate_child TERM INT", script)
        self.assertIn("CHILD_PID=\"$!\"", script)
        self.assertIn("wait \"$CHILD_PID\"", script)


if __name__ == "__main__":
    unittest.main()
