"""Tests for lib.schema (version validation + parsing)."""

import json
import os
import tempfile
import unittest

from lib.schema import (
    SchemaVersionError,
    load_payload,
    parse_version,
    require_schema_version,
    stamp,
)


class TestParseVersion(unittest.TestCase):
    def test_basic_major(self):
        self.assertEqual(parse_version("attendance-analysis/v1"), ("attendance-analysis", 1, 0))

    def test_major_minor(self):
        self.assertEqual(
            parse_version("portal-attendance-snapshot/v2.3"),
            ("portal-attendance-snapshot", 2, 3),
        )

    def test_malformed_no_slash(self):
        with self.assertRaises(SchemaVersionError):
            parse_version("attendance-analysis-v1")

    def test_malformed_no_version(self):
        with self.assertRaises(SchemaVersionError):
            parse_version("attendance-analysis")

    def test_empty_string(self):
        with self.assertRaises(SchemaVersionError):
            parse_version("")


class TestRequireSchemaVersion(unittest.TestCase):
    def test_matches_exact(self):
        require_schema_version(
            {"schema_version": "attendance-analysis/v1"}, "attendance-analysis/v1"
        )  # no raise

    def test_matches_minor_diff(self):
        # major matches, minor differs — accepted
        require_schema_version(
            {"schema_version": "attendance-analysis/v1.2"}, "attendance-analysis/v1"
        )

    def test_missing_field(self):
        with self.assertRaises(SchemaVersionError) as cm:
            require_schema_version({}, "attendance-analysis/v1")
        self.assertIn("schema_version", str(cm.exception))

    def test_wrong_name(self):
        with self.assertRaises(SchemaVersionError):
            require_schema_version({"schema_version": "other-schema/v1"}, "attendance-analysis/v1")

    def test_wrong_major(self):
        with self.assertRaises(SchemaVersionError):
            require_schema_version(
                {"schema_version": "attendance-analysis/v2"}, "attendance-analysis/v1"
            )

    def test_non_dict_payload(self):
        with self.assertRaises(SchemaVersionError):
            require_schema_version([], "attendance-analysis/v1")


class TestLoadPayload(unittest.TestCase):
    def _write_json(self, payload) -> str:
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        return path

    def test_round_trip(self):
        path = self._write_json({"schema_version": "attendance-analysis/v1", "x": 1})
        try:
            out = load_payload(path, "attendance-analysis/v1")
            self.assertEqual(out["x"], 1)
        finally:
            os.remove(path)

    def test_rejects_wrong_major(self):
        path = self._write_json({"schema_version": "attendance-analysis/v9", "x": 1})
        try:
            with self.assertRaises(SchemaVersionError):
                load_payload(path, "attendance-analysis/v1")
        finally:
            os.remove(path)


class TestStamp(unittest.TestCase):
    def test_stamps_in_place(self):
        d = {"x": 1}
        stamp(d, "attendance-analysis/v1")
        self.assertEqual(d["schema_version"], "attendance-analysis/v1")


if __name__ == "__main__":
    unittest.main()
