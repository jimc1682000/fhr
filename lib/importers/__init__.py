"""Importers turn external payloads into formats the fhr analyzer can consume.

Each importer reads a versioned schema (see `docs/schema/`) and emits
either an in-memory record list or a fhr-native artifact (e.g. the
9-column tab-delimited `.txt` attendance file)."""
