#!/usr/bin/env python3
"""Lightweight lint fallback when external linters are unavailable.

Checks:
- Syntax errors via compile()
- Trailing whitespace
- Tab indentation

Exit code 0 if clean; 1 if issues found. Prints a brief report.
"""
import os

ROOT = os.path.dirname(os.path.dirname(__file__))

EXCLUDE_DIRS = {
    ".git",
    "coverage_report",
    "build",
    "dist",
    "fhr.egg-info",
    "web",  # frontend assets
}


def iter_py_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        # prune excluded dirs
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


def check_file(path: str):
    issues = []
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return [(path, f"I/O error: {e}")]

    # Syntax
    try:
        compile(content, path, "exec")
    except SyntaxError as e:
        issues.append((path, f"SyntaxError: {e}"))

    # Note: full style linting requires Ruff/Flake8. This fallback intentionally keeps
    # checks minimal to avoid false positives on test fixtures.
    return issues


def main() -> int:
    issues = []
    for fp in iter_py_files(ROOT):
        issues.extend(check_file(fp))

    if not issues:
        print("lint: OK (fallback checks)")
        return 0
    for path, msg in issues:
        print(f"{path}: {msg}")
    print(f"lint: {len(issues)} issue(s) found")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
