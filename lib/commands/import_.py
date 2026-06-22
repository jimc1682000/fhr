"""`fhr import` — convert an external JSON snapshot into a fhr-native artifact.

Currently supports a single source (`portal-json`), which is the
`portal-attendance-snapshot/v1` shape that an agent-browser eval over
the 104 EHR Portal "全部刷卡資料" page produces. Output is the 9-column
tab-delimited .txt the analyzer ingests.

Legacy un-stamped JSON dumps (the kind this session captured ad-hoc)
are auto-promoted to v1 when `--legacy` is set."""

from __future__ import annotations

import argparse
import logging
import sys


def add_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "import",
        help="把外部 JSON 快照轉成 fhr 可吃的 .txt",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  # agent-browser eval 抓回來的出勤 snapshot → fhr .txt
  fhr import --from=portal-json snapshot.json \\
      --out=202604-202605-User-出勤資料.txt

  # 沒有 schema_version 的舊 dump → 自動補上 v1
  fhr import --from=portal-json legacy.json --legacy --out=out.txt
        """,
    )
    parser.add_argument("snapshot", help="輸入 JSON 路徑")
    parser.add_argument(
        "--from",
        dest="source",
        required=True,
        choices=["portal-json"],
        help="來源格式 (= schema 名稱)",
    )
    parser.add_argument("--out", required=True, help="輸出 .txt 路徑")
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="輸入是舊版未標 schema_version 的 dump，先 promote 再讀",
    )
    parser.add_argument("--debug", action="store_true", help="啟用 debug 模式")
    return parser


def run(args: argparse.Namespace) -> None:
    from attendance_analyzer import logger
    from lib.importers import portal_json as importer

    if args.debug:
        logger.setLevel(logging.DEBUG)

    try:
        if args.source == "portal-json":
            if args.legacy:
                snapshot = importer.snapshot_from_legacy_json(args.snapshot)
                records = importer.import_from_dict(snapshot)
            else:
                records = importer.import_snapshot(args.snapshot)
            importer.write_txt(args.out, records)
            logger.info("✅ %s (%d 筆)", args.out, len(records))
        else:
            logger.error("❌ 未支援的 --from=%s", args.source)
            sys.exit(2)
    except Exception as e:
        logger.error("❌ 錯誤: %s", e)
        sys.exit(1)
