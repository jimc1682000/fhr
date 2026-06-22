"""Tests for `lib/importers/portal_json.py`."""

import json
import os
import tempfile
import unittest

from lib.importers.portal_json import (
    HEADER_COLUMNS,
    SCHEMA_VERSION,
    convert_file,
    import_from_dict,
    import_snapshot,
    records_to_txt_lines,
    snapshot_from_legacy_json,
    write_txt,
)
from lib.schema import SchemaVersionError

SAMPLE_RECORDS = [
    {
        "scheduledTime": "2026/04/01 09:30",
        "actualTime": "2026/04/01 11:52",
        "type": "上班",
        "status": "遲到",
    },
    {
        "scheduledTime": "2026/04/01 18:30",
        "actualTime": "2026/04/01 19:49",
        "type": "下班",
        "status": "",
    },
    {
        "scheduledTime": "2026/04/10 09:30",
        "actualTime": "",
        "type": "上班",
        "status": "曠職",
    },
]


def _wrap(records):
    return {
        "schema_version": SCHEMA_VERSION,
        "totalPages": 1,
        "recordCount": len(records),
        "records": records,
    }


class TestRecordsToTxtLines(unittest.TestCase):
    def test_header_first(self):
        lines = records_to_txt_lines(SAMPLE_RECORDS)
        self.assertEqual(lines[0], "\t".join(HEADER_COLUMNS))

    def test_data_columns(self):
        lines = records_to_txt_lines(SAMPLE_RECORDS)
        # 9 columns each
        for line in lines:
            self.assertEqual(line.count("\t"), 8)

    def test_source_present_for_actual_punch(self):
        lines = records_to_txt_lines([SAMPLE_RECORDS[0]])
        cols = lines[1].split("\t")
        self.assertEqual(cols[4], "刷卡匯入")

    def test_source_empty_when_no_punch(self):
        # 曠職 record has no actual time → source must be blank
        lines = records_to_txt_lines([SAMPLE_RECORDS[2]])
        cols = lines[1].split("\t")
        self.assertEqual(cols[1], "")
        self.assertEqual(cols[4], "")

    def test_status_passthrough(self):
        lines = records_to_txt_lines(SAMPLE_RECORDS)
        # row 1 (after header) is 遲到
        self.assertEqual(lines[1].split("\t")[5], "遲到")
        # row 3 is 曠職
        self.assertEqual(lines[3].split("\t")[5], "曠職")

    def test_processed_column_always_empty(self):
        # 處理狀態 (col 6) MUST be empty so fhr's analyzer treats the records
        # as actionable rather than skipping them.
        lines = records_to_txt_lines(SAMPLE_RECORDS)
        for line in lines[1:]:
            self.assertEqual(line.split("\t")[6], "")


class TestImportSnapshot(unittest.TestCase):
    def _write(self, payload) -> str:
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        return path

    def test_round_trip(self):
        path = self._write(_wrap(SAMPLE_RECORDS))
        try:
            records = import_snapshot(path)
            self.assertEqual(len(records), 3)
            self.assertEqual(records[0]["status"], "遲到")
        finally:
            os.remove(path)

    def test_rejects_wrong_schema(self):
        path = self._write({"schema_version": "other/v1", "records": []})
        try:
            with self.assertRaises(SchemaVersionError):
                import_snapshot(path)
        finally:
            os.remove(path)

    def test_rejects_missing_records(self):
        path = self._write({"schema_version": SCHEMA_VERSION})
        try:
            with self.assertRaises(ValueError):
                import_snapshot(path)
        finally:
            os.remove(path)


class TestImportFromDict(unittest.TestCase):
    def test_happy_path(self):
        records = import_from_dict(_wrap(SAMPLE_RECORDS))
        self.assertEqual(len(records), 3)

    def test_rejects_wrong_major(self):
        with self.assertRaises(SchemaVersionError):
            import_from_dict(
                {"schema_version": f"{SCHEMA_VERSION.split('/')[0]}/v9", "records": []}
            )


class TestConvertFile(unittest.TestCase):
    def test_end_to_end(self):
        fd1, snap = tempfile.mkstemp(suffix=".json")
        os.close(fd1)
        fd2, out = tempfile.mkstemp(suffix=".txt")
        os.close(fd2)
        try:
            with open(snap, "w", encoding="utf-8") as f:
                json.dump(_wrap(SAMPLE_RECORDS), f)
            count = convert_file(snap, out)
            self.assertEqual(count, 3)
            content = open(out, encoding="utf-8").read()
            self.assertTrue(content.startswith("應刷卡時段\t當日卡鐘資料"))
            self.assertEqual(content.count("\n"), 4)  # header + 3 records + trailing \n
        finally:
            os.remove(snap)
            os.remove(out)


class TestSnapshotFromLegacyJson(unittest.TestCase):
    def _write(self, payload) -> str:
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        return path

    def test_legacy_dict_with_records(self):
        # The actual session's agent-browser eval produced this shape.
        path = self._write({"totalPages": 4, "recordCount": 62, "records": SAMPLE_RECORDS})
        try:
            promoted = snapshot_from_legacy_json(path)
            self.assertEqual(promoted["schema_version"], SCHEMA_VERSION)
            self.assertEqual(promoted["recordCount"], 62)
            self.assertEqual(len(promoted["records"]), 3)
        finally:
            os.remove(path)

    def test_legacy_bare_list(self):
        path = self._write(SAMPLE_RECORDS)
        try:
            promoted = snapshot_from_legacy_json(path)
            self.assertEqual(promoted["schema_version"], SCHEMA_VERSION)
            self.assertEqual(promoted["totalPages"], 1)
            self.assertEqual(promoted["recordCount"], 3)
        finally:
            os.remove(path)


class TestWriteTxt(unittest.TestCase):
    def test_writes_utf8_with_trailing_newline(self):
        fd, path = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        try:
            write_txt(path, SAMPLE_RECORDS)
            content = open(path, encoding="utf-8").read()
            self.assertTrue(content.endswith("\n"))
            # Verify analyzer-compatible by checking column count
            for line in content.rstrip("\n").splitlines():
                self.assertEqual(line.count("\t"), 8)
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
