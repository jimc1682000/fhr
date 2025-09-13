#!/usr/bin/env python3
"""Fail if project coverage percent is below a threshold.

Reads stdlib trace outputs from coverage_report/*.cover and computes the
overall coverage for project files (attendance_analyzer.py, lib/*.py).

Usage:
  python tools/check_coverage_threshold.py --min 95
"""
from pathlib import Path
import re
import argparse
import sys


def compute_percent(coverdir: Path) -> float:
    files = [p for p in coverdir.glob('*.cover') if p.name.startswith(('attendance_analyzer', 'lib.'))]
    executed = missing = 0
    for p in files:
        text = p.read_text(encoding='utf-8', errors='ignore').splitlines()
        executed += sum(1 for line in text if re.match(r'^\s*\d+\s*:', line))
        missing += sum(1 for line in text if line.strip().startswith('>>>>>>'))
    total = executed + missing
    if total == 0:
        return 100.0
    return executed / total * 100.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--min', dest='minimum', type=float, default=95.0, help='minimum coverage percent required')
    ap.add_argument('--dir', dest='coverdir', default='coverage_report', help='coverage directory')
    args = ap.parse_args()

    coverdir = Path(args.coverdir)
    if not coverdir.exists():
        print("coverage_report/ not found. Run 'make coverage' first.", file=sys.stderr)
        return 2

    pct = compute_percent(coverdir)
    print(f"Project coverage: {pct:.2f}% (required: {args.minimum:.2f}%)")
    if pct + 1e-9 < args.minimum:
        print("Coverage below threshold.", file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

