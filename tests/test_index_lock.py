import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("index_lock", ROOT / "scripts" / "index_lock.py")
index_lock = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(index_lock)


class IndexLockTests(unittest.TestCase):
    def test_acquire_writes_and_release_removes_lock_for_owner(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "index.lock"
            pid = os.getpid()

            index_lock.acquire_lock(lock_path, pid, "index")
            payload = index_lock.read_lock(lock_path)
            self.assertEqual(payload["pid"], pid)

            index_lock.release_lock(lock_path, pid)
            self.assertFalse(lock_path.exists())

    def test_acquire_refuses_live_existing_pid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "index.lock"
            pid = os.getpid()
            index_lock.acquire_lock(lock_path, pid, "index")

            with self.assertRaises(SystemExit) as raised:
                index_lock.acquire_lock(lock_path, pid + 1, "other index")

            self.assertIn(str(pid), str(raised.exception))

    def test_acquire_replaces_stale_lock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "index.lock"
            lock_path.write_text('{"pid": 999999999, "command": "old"}')

            index_lock.acquire_lock(lock_path, os.getpid(), "new")
            payload = index_lock.read_lock(lock_path)

            self.assertEqual(payload["command"], "new")

    def test_release_does_not_remove_another_owner_lock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "index.lock"
            index_lock.acquire_lock(lock_path, os.getpid(), "index")

            index_lock.release_lock(lock_path, os.getpid() + 1)

            self.assertTrue(lock_path.exists())


if __name__ == "__main__":
    unittest.main()
