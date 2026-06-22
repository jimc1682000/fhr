#!/usr/bin/env python3
"""Coverage gate with per-package baseline floors.

Reads stdlib trace outputs from `coverage_report/*.cover` and compares
each package's coverage against a baseline (`tools/coverage_baseline.json`).
CI fails if:
  - Overall % drops below `overall_min`
  - Any package drops more than `tolerance_pct` below its floor

Legacy usage `python tools/check_coverage_threshold.py --min 95` still
works (overrides the baseline file).

Usage:
  python tools/check_coverage_threshold.py                   # use baseline
  python tools/check_coverage_threshold.py --min 90          # legacy mode
  python tools/check_coverage_threshold.py --baseline tools/coverage_baseline.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# Package classifier — order matters (longest prefix wins).
PACKAGE_RULES: list[tuple[str, str]] = [
    ("attendance_analyzer", "attendance_analyzer"),
    ("lib.commands.", "lib.commands"),
    ("lib.portal.", "lib.portal"),
    ("lib.exporters.", "lib.io"),
    ("lib.importers.", "lib.io"),
    ("lib.", "lib.core"),
]


def _classify(name: str) -> str | None:
    for prefix, label in PACKAGE_RULES:
        if name.startswith(prefix):
            return label
    return None


def compute_per_package(coverdir: Path) -> dict[str, tuple[int, int]]:
    """Return {package_label: (executed_lines, missing_lines)}."""
    by_pkg: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for p in sorted(coverdir.glob("*.cover")):
        name = p.name.replace(".cover", "")
        label = _classify(name)
        if not label:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        executed = sum(1 for line in text if re.match(r"^\s*\d+\s*:", line))
        missing = sum(1 for line in text if line.strip().startswith(">>>>>>"))
        by_pkg[label][0] += executed
        by_pkg[label][1] += missing
    return {k: (ex, mi) for k, (ex, mi) in by_pkg.items()}


def _pct(ex: int, mi: int) -> float:
    total = ex + mi
    return 100.0 if total == 0 else ex / total * 100.0


def _summary(by_pkg: dict[str, tuple[int, int]]) -> tuple[float, dict[str, float]]:
    pcts = {pkg: _pct(ex, mi) for pkg, (ex, mi) in by_pkg.items()}
    total_ex = sum(ex for ex, _ in by_pkg.values())
    total_mi = sum(mi for _, mi in by_pkg.values())
    overall = _pct(total_ex, total_mi)
    return overall, pcts


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--min",
        dest="legacy_min",
        type=float,
        default=None,
        help="Legacy mode — single overall threshold; skips per-package baseline check.",
    )
    ap.add_argument(
        "--baseline",
        default="tools/coverage_baseline.json",
        help="Per-package baseline JSON (default: %(default)s)",
    )
    ap.add_argument(
        "--dir",
        dest="coverdir",
        default="coverage_report",
        help="Coverage directory (default: %(default)s)",
    )
    args = ap.parse_args()

    coverdir = Path(args.coverdir)
    if not coverdir.exists():
        print("coverage_report/ not found. Run 'make coverage' first.", file=sys.stderr)
        return 2

    by_pkg = compute_per_package(coverdir)
    overall, pcts = _summary(by_pkg)

    # ---- Legacy single-threshold mode ----
    if args.legacy_min is not None:
        print(f"Project coverage: {overall:.2f}% (required: {args.legacy_min:.2f}%)")
        if overall + 1e-9 < args.legacy_min:
            print("Coverage below threshold.", file=sys.stderr)
            return 1
        return 0

    # ---- Baseline mode ----
    baseline_path = Path(args.baseline)
    if not baseline_path.is_file():
        print(f"Baseline file not found: {baseline_path}", file=sys.stderr)
        return 2
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    tolerance = float(baseline.get("tolerance_pct", 0.0))
    overall_min = float(baseline.get("overall_min", 0.0))
    pkg_floors: dict[str, float] = baseline.get("packages", {})

    print(f"{'package':<22} {'pct':>8}  {'floor':>8}  status")
    print("-" * 56)
    failed: list[str] = []
    for pkg in sorted(set(pcts) | set(pkg_floors)):
        actual = pcts.get(pkg)
        floor = pkg_floors.get(pkg)
        if actual is None:
            print(f"{pkg:<22} {'(no data)':>8}  {floor:>8.2f}  ⚠️ no .cover files")
            continue
        floor_disp = f"{floor:.2f}" if floor is not None else "—"
        if floor is not None and actual + tolerance + 1e-9 < floor:
            failed.append(
                f"{pkg}: {actual:.2f}% drops more than {tolerance}pt below floor {floor:.2f}%"
            )
            print(f"{pkg:<22} {actual:>7.2f}%  {floor_disp:>8}  ❌ FAIL")
        else:
            print(f"{pkg:<22} {actual:>7.2f}%  {floor_disp:>8}  ✓ ok")

    print("-" * 56)
    overall_ok = overall + 1e-9 >= overall_min
    print(
        f"{'OVERALL':<22} {overall:>7.2f}%  {overall_min:>8.2f}  "
        f"{'✓ ok' if overall_ok else '❌ FAIL'}"
    )
    if not overall_ok:
        failed.append(f"overall: {overall:.2f}% < min {overall_min:.2f}%")

    if failed:
        print("\nCoverage check failed:", file=sys.stderr)
        for f in failed:
            print(f"  - {f}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
