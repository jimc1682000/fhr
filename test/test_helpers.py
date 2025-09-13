"""Category: Helpers
Purpose: Shared test helpers to reduce duplication and speed up tests.

Utilities:
- DummyResp: minimal urllib response stub with .read() bytes.
- temp_env: context manager to temporarily set environment variables.
- urlopen_sequence: build a side_effect for urlopen that yields exceptions
  or DummyResp-wrapped payloads in order.
"""

import json
import os
from contextlib import contextmanager


class DummyResp:
    """A minimal context manager simulating urllib responses.

    Usage:
        with urllib.request.urlopen(...) as resp:
            resp.read() -> bytes
    """

    def __init__(self, payload: dict):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@contextmanager
def temp_env(mapping=None, **overrides):
    """Temporarily set environment variables inside a context.

    Example:
        with temp_env({"HOLIDAY_API_MAX_RETRIES": "1"}, HOLIDAY_API_BACKOFF_BASE="0"):
            ...
    """
    new = dict(mapping or {})
    new.update({k: str(v) for k, v in overrides.items()})
    old = {}
    missing = set()
    for k, v in new.items():
        if k in os.environ:
            old[k] = os.environ[k]
        else:
            missing.add(k)
        os.environ[k] = str(v)
    try:
        yield
    finally:
        for k in new:
            if k in old:
                os.environ[k] = old[k]
            elif k in os.environ:
                del os.environ[k]


def urlopen_sequence(seq):
    """Return a side_effect function for urllib.request.urlopen.

    The sequence may contain exceptions or dict payloads (wrapped into DummyResp).
    """
    items = list(seq)

    def _side_effect(url, timeout=10, context=None):
        if not items:
            raise AssertionError("urlopen_sequence exhausted")
        v = items.pop(0)
        if isinstance(v, Exception):
            raise v
        if isinstance(v, dict):
            return DummyResp(v)
        return v

    return _side_effect
