import importlib.util
import os
import subprocess
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from index_state import IndexStatus


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("final_audit", ROOT / "scripts" / "final_audit.py")
final_audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(final_audit)


class FinalAuditTests(unittest.TestCase):
    def test_check_omlx_reports_missing_key(self):
        with patch.object(final_audit, "_get_omlx_api_key", return_value=None):
            ok, detail = final_audit.check_omlx()

        self.assertFalse(ok)
        self.assertIn("key not found", detail)

    def test_check_omlx_requires_selected_model(self):
        response = Mock()
        response.read.return_value = b'{"data": [{"id": "other-model"}]}'
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=None)
        with patch.object(final_audit, "_get_omlx_api_key", return_value="key"), patch.object(
            final_audit, "get_omlx_model_name", return_value="Gemma4-MTP-26B-BF16"
        ), patch.object(final_audit, "get_omlx_base_url", return_value="http://127.0.0.1:1234/v1"), patch.object(
            final_audit.urllib.request, "urlopen", return_value=context
        ):
            ok, detail = final_audit.check_omlx()

        self.assertFalse(ok)
        self.assertIn("Gemma4-MTP-26B-BF16", detail)
        self.assertIn("other-model", detail)

    def test_check_omlx_accepts_selected_model(self):
        response = Mock()
        response.read.return_value = b'{"data": [{"id": "Gemma4-MTP-26B-BF16"}]}'
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=None)
        with patch.object(final_audit, "_get_omlx_api_key", return_value="key"), patch.object(
            final_audit, "get_omlx_model_name", return_value="Gemma4-MTP-26B-BF16"
        ), patch.object(final_audit, "get_omlx_base_url", return_value="http://127.0.0.1:1234/v1"), patch.object(
            final_audit.urllib.request, "urlopen", return_value=context
        ):
            ok, detail = final_audit.check_omlx()

        self.assertTrue(ok)
        self.assertIn("available", detail)

    def test_run_final_validation_builds_rag_command(self):
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="Validation OK\n",
            stderr="",
        )
        with patch.object(final_audit.subprocess, "run", return_value=completed) as run:
            ok, detail = final_audit.run_final_validation(skip_rag=False)

        self.assertTrue(ok)
        self.assertEqual(detail, "Validation OK")
        self.assertEqual(run.call_args.args[0], ["scripts/validate_rag.sh", "--require-full-index", "--rag"])

    def test_run_final_validation_can_skip_rag(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="Validation OK\n", stderr="")
        with patch.object(final_audit.subprocess, "run", return_value=completed) as run:
            ok, _ = final_audit.run_final_validation(skip_rag=True)

        self.assertTrue(ok)
        self.assertEqual(run.call_args.args[0], ["scripts/validate_rag.sh", "--require-full-index"])

    def test_run_app_smoke_returns_combined_failure_output(self):
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="app failed\n",
        )
        with patch.object(final_audit.subprocess, "run", return_value=completed):
            ok, detail = final_audit.run_app_smoke()

        self.assertFalse(ok)
        self.assertEqual(detail, "app failed")

    def test_run_launchd_validation_returns_output(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="Validated app\n", stderr="")
        with patch.object(final_audit.subprocess, "run", return_value=completed) as run:
            ok, detail = final_audit.run_launchd_validation()

        self.assertTrue(ok)
        self.assertEqual(detail, "Validated app")
        self.assertEqual(run.call_args.args[0], ["scripts/launchd_manage.sh", "validate"])

    def test_check_docker_assets_accepts_expected_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "Dockerfile").write_text(
                'EXPOSE 8501\nHEALTHCHECK CMD curl http://127.0.0.1:8501/\nCMD ["streamlit", "run", "app.py", "--server.address", "0.0.0.0"]\n'
            )
            (root / "docker-compose.yml").write_text(
                "services:\n"
                "  epstein-rag:\n"
                "    environment:\n"
                "      OMLX_BASE_URL: http://host.docker.internal:1234/v1\n"
                "    volumes:\n"
                "      - ./data:/app/data\n"
                "      - ./chroma_db:/app/chroma_db\n"
                "    healthcheck:\n"
                "      test: curl\n"
            )
            (root / ".dockerignore").write_text("data\nchroma_db\n")
            with patch.object(final_audit, "ROOT", root):
                ok, detail = final_audit.check_docker_assets()

        self.assertTrue(ok)
        self.assertIn("oMLX host routing", detail)

    def test_check_docker_assets_rejects_missing_host_routing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "Dockerfile").write_text('EXPOSE 8501\nHEALTHCHECK CMD curl\nCMD ["streamlit", "--server.address", "0.0.0.0"]\n')
            (root / "docker-compose.yml").write_text(
                "services:\n  epstein-rag:\n    volumes:\n      - ./data:/app/data\n      - ./chroma_db:/app/chroma_db\n    healthcheck:\n      test: curl\n"
            )
            (root / ".dockerignore").write_text("data\nchroma_db\n")
            with patch.object(final_audit, "ROOT", root):
                ok, detail = final_audit.check_docker_assets()

        self.assertFalse(ok)
        self.assertIn("host", detail)

    def test_check_index_lock_accepts_live_lock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "index.lock"
            lock_path.write_text(f'{{"pid": {os.getpid()}, "command": "index"}}')
            with patch.object(final_audit, "index_lock_path", return_value=lock_path):
                ok, detail = final_audit.check_index_lock(indexing_active=True)

        self.assertTrue(ok)
        self.assertIn(str(os.getpid()), detail)

    def test_check_index_lock_rejects_missing_lock_during_active_indexing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(final_audit, "index_lock_path", return_value=Path(tmpdir) / "missing.lock"):
                ok, detail = final_audit.check_index_lock(indexing_active=True)

        self.assertFalse(ok)
        self.assertIn("no lock", detail)

    def test_check_index_lock_rejects_stale_lock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "index.lock"
            lock_path.write_text('{"pid": 999999999, "command": "old"}')
            with patch.object(final_audit, "index_lock_path", return_value=lock_path):
                ok, detail = final_audit.check_index_lock(indexing_active=False)

        self.assertFalse(ok)
        self.assertIn("stale", detail)

    def test_check_index_lock_accepts_no_lock_when_idle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(final_audit, "index_lock_path", return_value=Path(tmpdir) / "missing.lock"):
                ok, detail = final_audit.check_index_lock(indexing_active=False)

        self.assertTrue(ok)
        self.assertIn("no active", detail)

    def test_clean_stale_index_lock_removes_dead_owner_lock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "index.lock"
            lock_path.write_text('{"pid": 999999999, "command": "old"}')
            with patch.object(final_audit, "index_lock_path", return_value=lock_path):
                cleaned = final_audit.clean_stale_index_lock()

        self.assertTrue(cleaned)
        self.assertFalse(lock_path.exists())

    def test_check_index_progress_accepts_inactive_indexer(self):
        ok, detail = final_audit.check_index_progress(indexing_active=False)

        self.assertTrue(ok)
        self.assertIn("no active", detail)

    def test_check_index_progress_accepts_fresh_active_indexer(self):
        payload = {
            "stale": False,
            "stale_seconds": 600,
            "indexer_process_missing": False,
            "indexing_active": True,
            "index_lock": {"present": True, "stale": False},
            "manifest_age_seconds": 2,
            "index_log_age_seconds": 3,
        }
        with patch.object(final_audit, "progress_payload", return_value=payload):
            ok, detail = final_audit.check_index_progress(indexing_active=True)

        self.assertTrue(ok)
        self.assertIn("fresh", detail)

    def test_check_index_progress_rejects_stale_active_indexer(self):
        payload = {
            "stale": True,
            "stale_seconds": 60,
            "indexer_process_missing": False,
            "indexing_active": True,
            "index_lock": {"present": True, "stale": False},
            "manifest_age_seconds": 120,
            "index_log_age_seconds": 120,
        }
        with patch.object(final_audit, "progress_payload", return_value=payload):
            ok, detail = final_audit.check_index_progress(indexing_active=True)

        self.assertFalse(ok)
        self.assertIn("quiet", detail)

    def test_check_disk_space_accepts_sufficient_space(self):
        usage = Mock(total=100 * 1024**3, free=50 * 1024**3)
        with patch.object(final_audit.shutil, "disk_usage", return_value=usage), patch.dict(
            os.environ, {"MIN_FREE_DISK_GB": "20"}, clear=False
        ):
            ok, detail = final_audit.check_disk_space()

        self.assertTrue(ok)
        self.assertIn("50.0 GB free", detail)

    def test_check_disk_space_rejects_low_space(self):
        usage = Mock(total=100 * 1024**3, free=5 * 1024**3)
        with patch.object(final_audit.shutil, "disk_usage", return_value=usage), patch.dict(
            os.environ, {"MIN_FREE_DISK_GB": "20"}, clear=False
        ):
            ok, detail = final_audit.check_disk_space()

        self.assertFalse(ok)
        self.assertIn("minimum 20.0 GB", detail)

    def test_check_faiss_backend_requires_complete_index(self):
        with patch.object(
            final_audit,
            "faiss_progress_payload",
            return_value={"chunks": 100, "expected_chunks": 200, "complete": False},
        ):
            ok, detail = final_audit.check_faiss_backend()

        self.assertFalse(ok)
        self.assertIn("100/200", detail)

    def test_check_faiss_backend_accepts_complete_matching_index(self):
        with patch.object(
            final_audit,
            "faiss_progress_payload",
            return_value={"chunks": 200, "expected_chunks": 200, "metadata_chunks": 200, "complete": True},
        ):
            ok, detail = final_audit.check_faiss_backend()

        self.assertTrue(ok)
        self.assertIn("complete", detail)

    def test_check_chroma_backend_accepts_readable_caught_up_index(self):
        with patch.object(
            final_audit,
            "inspect_chroma",
            return_value={"embeddings": 10, "vector_gap": 0, "vector_caught_up": True},
        ), patch.object(final_audit, "validate_reader") as reader:
            ok, detail = final_audit.check_chroma_backend()

        self.assertTrue(ok)
        self.assertIn("readable", detail)
        reader.assert_called_once_with(final_audit.DB_DIR, 10)

    def test_check_chroma_backend_rejects_vector_gap(self):
        with patch.object(
            final_audit,
            "inspect_chroma",
            return_value={"embeddings": 10, "vector_gap": 2, "vector_caught_up": False},
        ):
            ok, detail = final_audit.check_chroma_backend()

        self.assertFalse(ok)
        self.assertIn("not caught up", detail)

    def test_audit_payload_reports_incomplete_index(self):
        status = IndexStatus(
            downloaded_files=2,
            expected_files=2,
            indexed_files=1,
            in_progress_files=1,
            indexed_docs=10,
            indexed_chunks=20,
            in_progress_names=("epstein_files-0001.parquet",),
            missing_indexed_names=("epstein_files-0001.parquet",),
        )
        with patch.object(final_audit, "read_index_status", return_value=status), patch.object(
            final_audit, "check_omlx", return_value=(True, "ok")
        ), patch.object(final_audit, "clean_stale_index_lock", return_value=False), patch.object(
            final_audit, "check_index_lock", return_value=(True, "lock ok")
        ), patch.object(
            final_audit, "check_index_progress", return_value=(True, "progress ok")
        ), patch.object(
            final_audit, "check_disk_space", return_value=(True, "disk ok")
        ), patch.object(
            final_audit, "check_chroma_backend", return_value=(True, "chroma ok")
        ), patch.object(
            final_audit, "check_faiss_backend", return_value=(True, "faiss ok")
        ), patch.object(
            final_audit, "check_docker_assets", return_value=(True, "docker ok")
        ), patch.object(
            final_audit, "run_launchd_validation", return_value=(True, "launchd ok")
        ), patch.object(
            final_audit,
            "progress_payload",
            return_value={
                "data": {"path": "data", "resolved_path": "/real/data", "size_human": "317.2 GB"},
                "index_storage": {"path": "chroma_db", "size_human": "21.0 GB"},
                "rate_files_per_minute": 2.5,
                "eta_seconds": 120,
                "eta_at_utc": "2026-06-01T04:00:00+00:00",
                "eta_at_local": "2026-05-31T21:00:00-07:00",
                "projected_index_size_human": "31.0 GB",
                "manifest_age_seconds": 2,
                "index_log_age_seconds": 3,
            },
        ):
            payload = final_audit.audit_payload(skip_app=True)

        self.assertFalse(payload["complete"])
        self.assertEqual(payload["index"]["indexed_files"], 1)
        self.assertEqual(payload["index"]["indexed_fraction"], 0.5)
        self.assertEqual(payload["index"]["missing_indexed_files"], 1)
        self.assertEqual(payload["index"]["missing_indexed_sample"], ["epstein_files-0001.parquet"])
        self.assertEqual(payload["index"]["unexpected_indexed_sample"], [])
        self.assertEqual(payload["progress"]["data"]["size_human"], "317.2 GB")
        self.assertEqual(payload["progress"]["index_storage"]["size_human"], "21.0 GB")
        self.assertEqual(payload["progress"]["projected_index_size_human"], "31.0 GB")
        self.assertEqual(payload["progress"]["rate_files_per_minute"], 2.5)
        self.assertEqual(payload["progress"]["eta_at_local"], "2026-05-31T21:00:00-07:00")
        full_index_gate = next(gate for gate in payload["gates"] if gate["key"] == "full_index")
        self.assertFalse(full_index_gate["ok"])
        self.assertTrue(payload["gates"][-1]["skipped"])

    def test_audit_payload_runs_validation_after_complete_index(self):
        status = IndexStatus(
            downloaded_files=2,
            expected_files=2,
            indexed_files=2,
            in_progress_files=0,
            indexed_docs=10,
            indexed_chunks=20,
            in_progress_names=(),
        )
        with patch.object(final_audit, "read_index_status", return_value=status), patch.object(
            final_audit, "check_omlx", return_value=(True, "ok")
        ), patch.object(final_audit, "clean_stale_index_lock", return_value=False), patch.object(
            final_audit, "check_index_lock", return_value=(True, "lock ok")
        ), patch.object(
            final_audit, "check_index_progress", return_value=(True, "progress ok")
        ), patch.object(
            final_audit, "check_disk_space", return_value=(True, "disk ok")
        ), patch.object(
            final_audit, "check_chroma_backend", return_value=(True, "chroma ok")
        ), patch.object(
            final_audit, "check_faiss_backend", return_value=(True, "faiss ok")
        ), patch.object(
            final_audit, "check_docker_assets", return_value=(True, "docker ok")
        ), patch.object(
            final_audit, "run_launchd_validation", return_value=(True, "launchd ok")
        ), patch.object(
            final_audit, "run_app_smoke", return_value=(True, "app ok")
        ), patch.object(
            final_audit, "run_final_validation", return_value=(True, "Validation OK")
        ) as validate:
            payload = final_audit.audit_payload(skip_app=False, skip_rag=True)

        self.assertFalse(payload["complete"])
        self.assertIn("rag_generation", payload["skipped_gates"])
        validate.assert_called_once_with(True)

    def test_audit_payload_is_complete_only_when_no_gate_is_skipped(self):
        status = IndexStatus(
            downloaded_files=2,
            expected_files=2,
            indexed_files=2,
            in_progress_files=0,
            indexed_docs=10,
            indexed_chunks=20,
            in_progress_names=(),
        )
        with patch.object(final_audit, "read_index_status", return_value=status), patch.object(
            final_audit, "check_omlx", return_value=(True, "ok")
        ), patch.object(final_audit, "clean_stale_index_lock", return_value=False), patch.object(
            final_audit, "check_index_lock", return_value=(True, "lock ok")
        ), patch.object(
            final_audit, "check_index_progress", return_value=(True, "progress ok")
        ), patch.object(
            final_audit, "check_disk_space", return_value=(True, "disk ok")
        ), patch.object(
            final_audit, "check_chroma_backend", return_value=(True, "chroma ok")
        ), patch.object(
            final_audit, "check_faiss_backend", return_value=(True, "faiss ok")
        ), patch.object(
            final_audit, "check_docker_assets", return_value=(True, "docker ok")
        ), patch.object(
            final_audit, "run_launchd_validation", return_value=(True, "launchd ok")
        ), patch.object(
            final_audit, "run_app_smoke", return_value=(True, "app ok")
        ), patch.object(
            final_audit, "run_final_validation", return_value=(True, "Validation OK")
        ) as validate:
            payload = final_audit.audit_payload(skip_app=False, skip_rag=False)

        self.assertTrue(payload["complete"])
        self.assertEqual(payload["skipped_gates"], [])
        validate.assert_called_once_with(False)

    def test_audit_payload_is_not_complete_when_app_is_skipped(self):
        status = IndexStatus(
            downloaded_files=2,
            expected_files=2,
            indexed_files=2,
            in_progress_files=0,
            indexed_docs=10,
            indexed_chunks=20,
            in_progress_names=(),
        )
        with patch.object(final_audit, "read_index_status", return_value=status), patch.object(
            final_audit, "check_omlx", return_value=(True, "ok")
        ), patch.object(final_audit, "clean_stale_index_lock", return_value=False), patch.object(
            final_audit, "check_index_lock", return_value=(True, "lock ok")
        ), patch.object(
            final_audit, "check_index_progress", return_value=(True, "progress ok")
        ), patch.object(
            final_audit, "check_disk_space", return_value=(True, "disk ok")
        ), patch.object(
            final_audit, "check_chroma_backend", return_value=(True, "chroma ok")
        ), patch.object(
            final_audit, "check_faiss_backend", return_value=(True, "faiss ok")
        ), patch.object(
            final_audit, "check_docker_assets", return_value=(True, "docker ok")
        ), patch.object(
            final_audit, "run_launchd_validation", return_value=(True, "launchd ok")
        ), patch.object(
            final_audit, "run_final_validation", return_value=(True, "Validation OK")
        ):
            payload = final_audit.audit_payload(skip_app=True, skip_rag=False)

        self.assertFalse(payload["complete"])
        self.assertIn("streamlit_app", payload["skipped_gates"])

    def test_print_human_includes_active_index_progress(self):
        payload = {
            "gates": [
                {"ok": True, "label": "Dataset", "detail": "2/2 parquet files"},
                {"ok": False, "label": "Full index", "detail": "1/2 files"},
            ],
            "progress": {
                "rate_files_per_minute": 2.5,
                "eta_seconds": 120,
                "eta_at_local": "2026-05-31T21:00:00-07:00",
            },
        }

        with patch("sys.stdout", new_callable=StringIO) as stdout:
            final_audit.print_human(payload)

        output = stdout.getvalue()
        self.assertIn("Index rate: 2.50 files/min", output)
        self.assertIn("Index ETA: 2m 0s", output)
        self.assertIn("2026-05-31T21:00:00-07:00", output)


if __name__ == "__main__":
    unittest.main()
