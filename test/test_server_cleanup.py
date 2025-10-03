import json
import os
import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    TestClient = None
    service = None
else:  # pragma: no cover
    import server.main as service


def _build_test_client(tmpdir: str) -> tuple[TestClient, callable]:
    if service is None:  # pragma: no cover - guard when fastapi missing
        raise RuntimeError("FastAPI not available")

    original_upload = service.UPLOAD_DIR
    original_output = service.OUTPUT_ROOT
    original_canonical = service.CANONICAL_OUTPUT_DIR

    uploads = os.path.join(tmpdir, "uploads")
    outputs = os.path.join(tmpdir, "outputs")
    canonical = os.path.join(outputs, "canonical")
    os.makedirs(uploads, exist_ok=True)
    os.makedirs(canonical, exist_ok=True)

    service.UPLOAD_DIR = uploads
    service.OUTPUT_ROOT = outputs
    service.CANONICAL_OUTPUT_DIR = canonical

    app = service.create_app()
    client = TestClient(app)

    def restore() -> None:
        service.UPLOAD_DIR = original_upload
        service.OUTPUT_ROOT = original_output
        service.CANONICAL_OUTPUT_DIR = original_canonical

    return client, restore


@unittest.skipUnless(TestClient, "fastapi not available")
class TestServerCleanup(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.client, self.restore = _build_test_client(self.tmpdir.name)
        self.addCleanup(self.restore)
        self.addCleanup(self.tmpdir.cleanup)
        self.canonical_dir = Path(service.CANONICAL_OUTPUT_DIR)

    def _preview(
        self,
        *,
        filename: str,
        output: str = "csv",
        debug: bool = False,
        policy: str = "merge",
    ):
        response = self.client.post(
            "/api/exports/cleanup-preview",
            json={
                "filename": filename,
                "output": output,
                "debug": debug,
                "export_policy": policy,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _analyze(self, *, file_path: str, cleanup_state: dict, snapshot: dict | None = None):
        with open(file_path, "rb") as fh:
            data = {
                "mode": "incremental",
                "output": cleanup_state["output"],
                "reset_state": "false",
                "debug": "true" if cleanup_state["debug"] else "false",
                "export_policy": cleanup_state["export_policy"],
                "cleanup_exports": "true" if cleanup_state["enabled"] else "false",
            }
            if snapshot:
                data["cleanup_token"] = snapshot["token"]
                data["cleanup_snapshot"] = json.dumps(snapshot["snapshot"])

            response = self.client.post(
                "/api/analyze",
                data=data,
                files={"file": (os.path.basename(file_path), fh, "text/plain")},
            )
        return response

    def _write_canonical(self, name: str, content: str) -> Path:
        path = self.canonical_dir / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_cleanup_preview_and_analyze_merges_backups(self):
        canonical = self._write_canonical(
            "sample-attendance-data_analysis.csv", "old,data\n"
        )
        self._write_canonical(
            "sample-attendance-data_analysis_20240101_000000.csv", "backup,data\n"
        )

        preview = self._preview(filename="sample-attendance-data.txt", output="csv")
        backup_names = {item["name"] for item in preview["items"] if item["kind"] == "backup"}
        self.assertIn("sample-attendance-data_analysis_20240101_000000.csv", backup_names)
        canonical_entry = [item for item in preview["items"] if item["kind"] == "canonical"]
        self.assertTrue(canonical_entry)
        self.assertFalse(canonical_entry[0]["delete"])

        cleanup_state = {
            "output": "csv",
            "debug": False,
            "export_policy": "merge",
            "enabled": True,
        }
        response = self._analyze(
            file_path=os.path.join(os.getcwd(), "sample-attendance-data.txt"),
            cleanup_state=cleanup_state,
            snapshot=preview,
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["cleanup"]["status"], "performed")
        backup_path = self.canonical_dir / "sample-attendance-data_analysis_20240101_000000.csv"
        self.assertFalse(backup_path.exists())
        self.assertTrue(canonical.exists())

    def test_cleanup_requires_preview_token(self):
        cleanup_state = {
            "output": "csv",
            "debug": False,
            "export_policy": "merge",
            "enabled": True,
        }
        response = self._analyze(
            file_path=os.path.join(os.getcwd(), "sample-attendance-data.txt"),
            cleanup_state=cleanup_state,
            snapshot=None,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cleanup_preview_required")


if __name__ == "__main__":
    unittest.main()
