"""Tests for `tools/diff_screenshots.py` (Tier 4).

Requires Pillow (declared in `requirements-dev.txt`). Tests skip when
Pillow is not installed so the suite still passes in stripped-down envs.
"""

import tempfile
import unittest
from pathlib import Path

try:
    from PIL import Image, ImageDraw  # noqa: F401

    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PNG = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "screenshot_baselines"
    / "dry-run"
    / "overtime-20260420-1830-2030.png"
)


@unittest.skipUnless(_HAS_PIL, "Pillow not installed")
class TestDiffScreenshots(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _copy(self) -> str:
        import shutil

        dest = Path(self.tmpdir) / "copy.png"
        shutil.copyfile(SAMPLE_PNG, dest)
        return str(dest)

    def _paint(self, fraction: float) -> str:
        """Paint `fraction` of the canvas (top stripe) with red. Returns path."""
        from PIL import Image, ImageDraw  # type: ignore

        img = Image.open(SAMPLE_PNG).copy()
        w, h = img.size
        ImageDraw.Draw(img).rectangle([0, 0, w, int(h * fraction)], fill="red")
        dest = Path(self.tmpdir) / f"painted-{fraction}.png"
        img.save(dest)
        return str(dest)

    def test_identical_returns_zero(self):
        from tools.diff_screenshots import diff

        res = diff(self._copy(), str(SAMPLE_PNG))
        self.assertEqual(res.diff_ratio, 0.0)
        self.assertFalse(res.size_mismatch)

    def test_small_change_under_threshold(self):
        from tools.diff_screenshots import diff

        res = diff(self._paint(0.01), str(SAMPLE_PNG))
        # Painted 1% of canvas → diff ratio should be ~0.01
        self.assertTrue(res.is_within(0.05), f"diff_ratio={res.diff_ratio} should be within 5%")

    def test_big_change_over_threshold(self):
        from tools.diff_screenshots import diff

        res = diff(self._paint(0.5), str(SAMPLE_PNG))
        # Top 50% painted → diff ratio ≈ 0.5
        self.assertFalse(res.is_within(0.05))
        self.assertGreater(res.diff_ratio, 0.4)

    def test_size_mismatch(self):
        from PIL import Image  # type: ignore

        from tools.diff_screenshots import diff

        small = Path(self.tmpdir) / "small.png"
        Image.new("RGB", (10, 10), "white").save(small)
        res = diff(str(small), str(SAMPLE_PNG))
        self.assertTrue(res.size_mismatch)
        self.assertEqual(res.diff_ratio, 1.0)


@unittest.skipUnless(_HAS_PIL, "Pillow not installed")
class TestDiffScreenshotsCLI(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_cli_exit_codes(self):
        import subprocess
        import sys

        cmd = [
            sys.executable,
            str(REPO_ROOT / "tools" / "diff_screenshots.py"),
            str(SAMPLE_PNG),
            str(SAMPLE_PNG),
            "--quiet",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)

    def test_cli_missing_file(self):
        import subprocess
        import sys

        cmd = [
            sys.executable,
            str(REPO_ROOT / "tools" / "diff_screenshots.py"),
            "/no/such/file.png",
            str(SAMPLE_PNG),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
