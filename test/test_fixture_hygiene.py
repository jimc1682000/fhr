"""Fixtures in this public repo must be synthetic.

A real Portal capture shows names, employee numbers and phone numbers, and
text scanners cannot read pixels. So every committed image has to carry the
`fhr-synthetic` PNG text chunk that the fixture generator writes; a capture
copied in from `tmp/dry-run-screenshots/` won't have it. Keep real captures
under `tests/fixtures/real/`, which is gitignored.
"""

import subprocess
import unittest
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent


def _tracked_pngs() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.png"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    if out.returncode != 0:  # not a git checkout (e.g. sdist); fall back to a walk
        return sorted((REPO_ROOT / "tests" / "fixtures").rglob("*.png"))
    return [REPO_ROOT / line for line in out.stdout.splitlines() if line]


class TestFixtureHygiene(unittest.TestCase):
    def test_every_png_is_marked_synthetic(self) -> None:
        unmarked = []
        for path in _tracked_pngs():
            with Image.open(path) as im:
                if im.info.get("fhr-synthetic") != "1":
                    unmarked.append(str(path.relative_to(REPO_ROOT)))
        self.assertEqual(unmarked, [], "real captures belong in tests/fixtures/real/")


if __name__ == "__main__":
    unittest.main()
