#!/usr/bin/env python3
"""Generate a local SVG coverage badge from coverage_report/*.cover.

This parses stdlib trace outputs to compute an overall percentage for
project files (attendance_analyzer.py and lib/*.py), then writes an SVG badge
to assets/coverage.svg.
"""
import os
import re
from pathlib import Path


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


def render_svg(percent: float) -> str:
    pct = int(round(percent))
    # Choose color roughly following shields.io semantics
    if pct >= 90:
        color = '#4c1'  # brightgreen
    elif pct >= 80:
        color = '#97CA00'  # greenish
    elif pct >= 70:
        color = '#a4a61d'  # yellowgreen
    elif pct >= 60:
        color = '#dfb317'  # yellow
    elif pct >= 50:
        color = '#fe7d37'  # orange
    else:
        color = '#e05d44'  # red

    label = 'coverage'
    value = f'{pct}%'

    # Basic, self-contained SVG (no external fonts). Widths approximate.
    # Left (label) 78px, Right (value) depends on digits; fixed 54px works up to 100%.
    left_w = 78
    right_w = 54
    total_w = left_w + right_w
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="20" role="img" aria-label="{label}: {value}">
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <mask id="m"><rect width="{total_w}" height="20" rx="3" fill="#fff"/></mask>
  <g mask="url(#m)">
    <rect width="{left_w}" height="20" fill="#555"/>
    <rect x="{left_w}" width="{right_w}" height="20" fill="{color}"/>
    <rect width="{total_w}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
    <text x="{left_w/2}" y="15" fill="#010101" fill-opacity=".3">{label}</text>
    <text x="{left_w/2}" y="14">{label}</text>
    <text x="{left_w + right_w/2}" y="15" fill="#010101" fill-opacity=".3">{value}</text>
    <text x="{left_w + right_w/2}" y="14">{value}</text>
  </g>
</svg>'''


def main() -> None:
    coverdir = Path('coverage_report')
    if not coverdir.exists():
        raise SystemExit("coverage_report/ not found. Run 'make coverage' first.")
    percent = compute_percent(coverdir)
    svg = render_svg(percent)

    assets = Path('assets')
    assets.mkdir(exist_ok=True)
    out = assets / 'coverage.svg'
    out.write_text(svg, encoding='utf-8')
    print(f'Wrote badge to {out} ({percent:.1f}%).')


if __name__ == '__main__':
    main()

