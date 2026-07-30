import os
import tempfile
import unittest
from unittest import mock

try:
    import fastapi  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    service = None
else:  # pragma: no cover
    from server import main as service


@unittest.skipUnless(service, "fastapi not available")
class TestServerRuntimePaths(unittest.TestCase):
    def test_build_root_uses_configured_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            configured = os.path.join(tmpdir, "runtime")
            with mock.patch.dict(os.environ, {"FHR_BUILD_DIR": configured}):
                self.assertEqual(service._resolve_build_root(), configured)

    def test_build_root_defaults_to_working_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ):
                os.environ.pop("FHR_BUILD_DIR", None)
                with mock.patch.object(service.os, "getcwd", return_value=tmpdir):
                    self.assertEqual(service._resolve_build_root(), os.path.join(tmpdir, "build"))

    def test_state_file_defaults_under_build_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ):
                os.environ.pop("FHR_STATE_FILE", None)
                with mock.patch.object(service, "BUILD_ROOT", tmpdir):
                    service.create_app()
                    self.assertEqual(
                        os.environ["FHR_STATE_FILE"],
                        os.path.join(tmpdir, "attendance_state.json"),
                    )


if __name__ == "__main__":
    unittest.main()
