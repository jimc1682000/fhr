#!/usr/bin/env python3
"""Compare a candidate PNG against a baseline PNG.

Used by Tier 4 of the v2.1 testing plan to catch Portal UI drift —
once we have recorded real screenshots, each `portal-apply --dry-run`
run via the replay test (`test_e2e_portal_replay.py`) can compare its
outputs against a checked-in baseline. A drift larger than a
configurable threshold fails the test, surfacing Portal layout changes
before they break a live submission.

Algorithm:
  - Load both PNGs via Pillow
  - If sizes differ → diff_ratio = 1.0 (treat as full mismatch)
  - Otherwise convert to RGB, build a per-pixel diff via
    `PIL.ImageChops.difference`, and count pixels whose max channel
    delta exceeds `pixel_tolerance` (default 16/255). Ratio of
    such pixels to total pixels = diff_ratio.

Threshold defaults to 5% pixel difference, which absorbs Chromium
anti-alias / font noise but flags structural changes (new fields,
moved buttons, color theme swap).
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DiffResult:
    diff_ratio: float            # 0.0 → identical, 1.0 → completely different
    size_mismatch: bool
    candidate_size: tuple[int, int]
    baseline_size: tuple[int, int]

    def is_within(self, threshold: float) -> bool:
        return (not self.size_mismatch) and self.diff_ratio <= threshold


def diff(candidate: str | Path, baseline: str | Path,
         *, pixel_tolerance: int = 16) -> DiffResult:
    """Compare two PNGs. Lazy Pillow import keeps fhr's hard deps zero."""
    from PIL import Image, ImageChops  # type: ignore

    c = Image.open(candidate).convert("RGB")
    b = Image.open(baseline).convert("RGB")
    if c.size != b.size:
        return DiffResult(
            diff_ratio=1.0, size_mismatch=True,
            candidate_size=c.size, baseline_size=b.size,
        )
    delta = ImageChops.difference(c, b)
    bbox = delta.getbbox()
    if bbox is None:
        # Identical → fast path
        return DiffResult(
            diff_ratio=0.0, size_mismatch=False,
            candidate_size=c.size, baseline_size=b.size,
        )
    # Reduce the delta to the changed bounding box only (fewer pixels to walk)
    region = delta.crop(bbox)
    # ImageStat.Stat is the supported Pillow API for aggregates; for our
    # threshold logic we need a per-pixel max — fall back to .tobytes().
    raw = region.tobytes()  # RGB rows
    n_rgb = len(raw)
    # Tally pixels whose max RGB delta exceeds the tolerance.
    changed = 0
    for i in range(0, n_rgb, 3):
        if (raw[i] > pixel_tolerance
                or raw[i + 1] > pixel_tolerance
                or raw[i + 2] > pixel_tolerance):
            changed += 1
    total_pixels = c.size[0] * c.size[1]
    return DiffResult(
        diff_ratio=changed / total_pixels if total_pixels else 0.0,
        size_mismatch=False,
        candidate_size=c.size, baseline_size=b.size,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidate", help="新截圖路徑")
    ap.add_argument("baseline", help="baseline 截圖路徑")
    ap.add_argument("--threshold", type=float, default=0.05,
                    help="可接受 pixel diff 比例 (預設 0.05 = 5%%)")
    ap.add_argument("--pixel-tolerance", type=int, default=16,
                    help="單像素 RGB 差 ≤ 此值視為相同 (預設 16/255)")
    ap.add_argument("--quiet", action="store_true",
                    help="只回 exit code,不印細節")
    args = ap.parse_args(argv)

    try:
        res = diff(args.candidate, args.baseline,
                   pixel_tolerance=args.pixel_tolerance)
    except FileNotFoundError as e:
        print(f"❌ 找不到檔案: {e.filename}", file=sys.stderr)
        return 2
    except ImportError:
        print("❌ Pillow 未安裝 — `pip install Pillow`", file=sys.stderr)
        return 3

    ok = res.is_within(args.threshold)
    if not args.quiet:
        if res.size_mismatch:
            print(f"❌ size mismatch: candidate {res.candidate_size} "
                  f"vs baseline {res.baseline_size}")
        else:
            verdict = "✓" if ok else "❌"
            print(f"{verdict} diff_ratio={res.diff_ratio:.4f} "
                  f"(threshold {args.threshold})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
