"""CLI orchestrator extracted from attendance_analyzer.main().

Keeps behavior-compatible semantics: normal runs do not call sys.exit,
error paths may call sys.exit(1) to match prior tests.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys


def run(argv: list | None = None) -> None:
    from attendance_analyzer import logger  # reuse shared logger
    from lib.service import (
        AnalysisError,
        AnalysisOptions,
        AnalyzerService,
        OutputRequest,
        ResetStateError,
    )

    parser = argparse.ArgumentParser(
        description='考勤分析系統 - 支援增量分析避免重複處理',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例用法:
  # 預設增量分析（推薦）
  python attendance_analyzer.py 202508-員工姓名-出勤資料.txt

  # 強制完整重新分析
  python attendance_analyzer.py 202508-員工姓名-出勤資料.txt --full

  # 清除使用者狀態後重新分析
  python attendance_analyzer.py 202508-員工姓名-出勤資料.txt --reset-state

  # 指定輸出格式
  python attendance_analyzer.py 202508-員工姓名-出勤資料.txt csv
        """
    )

    parser.add_argument('filepath', help='考勤檔案路徑')
    parser.add_argument('format', nargs='?', default='excel',
                        choices=['excel', 'csv'], help='輸出格式 (預設: excel)')
    parser.add_argument('--incremental', '-i', action='store_true', default=True,
                        help='啟用增量分析模式 (預設開啟)')
    parser.add_argument('--full', '-f', action='store_true',
                        help='強制完整重新分析')
    parser.add_argument('--reset-state', '-r', action='store_true',
                        help='清除指定使用者的狀態記錄')
    parser.add_argument('--debug', action='store_true',
                        help='啟用 debug 模式（詳細日誌、不寫入狀態檔）')

    args = parser.parse_args(argv[1:] if argv is not None else None)

    filepath = args.filepath
    format_type = args.format
    incremental_mode = args.incremental and not args.full
    mode = 'incremental' if incremental_mode else 'full'

    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("🐞 CLI Debug 模式啟動：將略過狀態寫入並輸出詳細訊息。")

    base, ext = os.path.splitext(filepath)
    if ext.lower() != '.txt':
        base = filepath

    primary_ext = '.xlsx' if format_type == 'excel' else '.csv'
    primary_output = OutputRequest(path=f"{base}_analysis{primary_ext}", format=format_type)

    extra_outputs = []
    if format_type == 'excel':
        extra_outputs.append(OutputRequest(path=f"{base}_analysis.csv", format='csv'))

    service = AnalyzerService()

    options = AnalysisOptions(
        source_path=filepath,
        requested_format=format_type,
        mode=mode,
        reset_state=args.reset_state,
        debug=args.debug,
        output=primary_output,
        extra_outputs=tuple(extra_outputs),
    )

    try:
        result = service.run(options)
    except ResetStateError as exc:
        logger.warning("⚠️  %s", exc)
        sys.exit(1)
    except AnalysisError as exc:
        logger.error("❌ 錯誤: %s", exc)
        sys.exit(1)

    logger.info("\n")
    for line in result.report_text.split('\n'):
        logger.info(line)

    if result.outputs:
        primary = result.outputs[0]
        if primary.actual_format == 'csv':
            logger.info("✅ CSV報告已匯出: %s", primary.actual_path)
        else:
            logger.info("✅ Excel報告已匯出: %s", primary.actual_path)
        for extra in result.outputs[1:]:
            if extra.actual_format == 'csv':
                logger.info("📝 同時匯出CSV格式: %s", extra.actual_path)
            else:
                logger.info("📝 另輸出Excel格式: %s", extra.actual_path)
