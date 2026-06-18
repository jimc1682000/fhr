"""Tests for `lib/env.py` (.env loader)."""

import os
import tempfile
import unittest
from pathlib import Path

from lib.env import _parse_line, find_dotenv, load


class TestParseLine(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(_parse_line("FOO=bar"), ("FOO", "bar"))

    def test_strip_whitespace(self):
        self.assertEqual(_parse_line("  FOO  =  bar  "), ("FOO", "bar"))

    def test_comment(self):
        self.assertIsNone(_parse_line("# comment"))
        self.assertIsNone(_parse_line("   # indented comment"))

    def test_blank(self):
        self.assertIsNone(_parse_line(""))
        self.assertIsNone(_parse_line("   "))

    def test_no_equals(self):
        self.assertIsNone(_parse_line("FOO"))

    def test_strips_double_quotes(self):
        self.assertEqual(_parse_line('FOO="bar baz"'), ("FOO", "bar baz"))

    def test_strips_single_quotes(self):
        self.assertEqual(_parse_line("FOO='bar baz'"), ("FOO", "bar baz"))

    def test_unbalanced_quotes_kept(self):
        self.assertEqual(_parse_line('FOO="bar'), ("FOO", '"bar'))

    def test_invalid_key(self):
        self.assertIsNone(_parse_line("FOO BAR=baz"))
        self.assertIsNone(_parse_line("=value"))


class TestFindDotenv(unittest.TestCase):
    def test_returns_none_when_absent(self):
        with tempfile.TemporaryDirectory() as d:
            sub = Path(d) / "sub" / "deep"
            sub.mkdir(parents=True)
            # Don't create a .env anywhere on this path
            # find_dotenv walks up to filesystem root — may match a real .env
            # in the developer's home directory, so we mock CWD by using
            # an explicit `start`.
            result = find_dotenv(sub)
            # We can't assert None reliably (real .env may exist higher up),
            # but if it does match, it must NOT be inside our tempdir.
            if result is not None:
                self.assertFalse(str(result).startswith(d))

    def test_finds_in_current_dir(self):
        with tempfile.TemporaryDirectory() as d:
            dotenv = Path(d) / ".env"
            dotenv.write_text("FOO=bar\n", encoding="utf-8")
            self.assertEqual(find_dotenv(d), dotenv.resolve())

    def test_walks_upward(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            dotenv = root / ".env"
            dotenv.write_text("FOO=bar\n", encoding="utf-8")
            deep = root / "a" / "b" / "c"
            deep.mkdir(parents=True)
            self.assertEqual(find_dotenv(deep), dotenv.resolve())


class TestLoad(unittest.TestCase):
    def _write(self, content: str) -> str:
        fd, path = tempfile.mkstemp(suffix=".env")
        os.close(fd)
        Path(path).write_text(content, encoding="utf-8")
        return path

    def setUp(self):
        self._saved_env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._saved_env)

    def test_injects_into_environ(self):
        path = self._write("EHR_URL=http://example.local\nEHR_COMPANY_NO=42\n")
        try:
            applied = load(path)
            self.assertEqual(applied["EHR_URL"], "http://example.local")
            self.assertEqual(os.environ["EHR_URL"], "http://example.local")
            self.assertEqual(os.environ["EHR_COMPANY_NO"], "42")
        finally:
            os.remove(path)

    def test_respects_existing_env(self):
        os.environ["EHR_URL"] = "from-shell"
        path = self._write("EHR_URL=from-dotenv\n")
        try:
            applied = load(path)
            self.assertNotIn("EHR_URL", applied)
            self.assertEqual(os.environ["EHR_URL"], "from-shell")
        finally:
            os.remove(path)

    def test_override_flag(self):
        os.environ["EHR_URL"] = "from-shell"
        path = self._write("EHR_URL=from-dotenv\n")
        try:
            applied = load(path, override=True)
            self.assertEqual(applied["EHR_URL"], "from-dotenv")
            self.assertEqual(os.environ["EHR_URL"], "from-dotenv")
        finally:
            os.remove(path)

    def test_missing_file_is_noop(self):
        applied = load("/no/such/file/.env")
        self.assertEqual(applied, {})

    def test_ignores_invalid_lines(self):
        path = self._write("VALID=ok\n# comment\nbroken line\nALSO=fine\n")
        try:
            applied = load(path)
            self.assertEqual(set(applied), {"VALID", "ALSO"})
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
