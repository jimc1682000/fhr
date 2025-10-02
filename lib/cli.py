"""CLI orchestrator extracted from attendance_analyzer.main().

Keeps behavior-compatible semantics: normal runs do not call sys.exit,
error paths may call sys.exit(1) to match prior tests.
"""
import argparse
import logging
import os
import sys
from datetime import datetime


def run(argv: list | None = None) -> None:
    from attendance_analyzer import AttendanceAnalyzer, logger  # reuse same logger
    from lib.filename import parse_range_and_user
    from lib.state import AttendanceStateManager

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
    parser.add_argument(
        '--export-policy',
        choices=['merge', 'archive'],
        default='merge',
        help='匯出策略：merge 直接覆寫主檔案，archive 保留 timestamp 備份。',
    )
    parser.add_argument(
        '--cleanup-exports',
        action='store_true',
        help='清除 timestamp 備份；搭配 --debug 時同時刪除本次產出的匯出檔案。',
    )

    args = parser.parse_args(argv[1:] if argv is not None else None)

    filepath = args.filepath
    format_type = args.format
    incremental_mode = args.incremental and not args.full
    export_policy = args.export_policy
    cleanup_exports = args.cleanup_exports

    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("🐞 CLI Debug 模式啟動：將略過狀態寫入並輸出詳細訊息。")

    if args.reset_state:
        # analyzer_temp = AttendanceAnalyzer()  # Variable assigned but never used
        user_name, _, _ = parse_range_and_user(filepath)
        if user_name:
            state_manager = AttendanceStateManager(read_only=args.debug)
            if args.debug:
                logger.debug("🛡️  Debug 模式：略過清除使用者 %s 的狀態", user_name)
            elif user_name in state_manager.state_data.get("users", {}):
                del state_manager.state_data["users"][user_name]
                state_manager.save_state()
                logger.info(
                    "🗑️  狀態檔 'attendance_state.json' 已清除使用者 %s 的記錄 @ %s",
                    user_name,
                    datetime.now().isoformat(),
                )
            else:
                logger.info("ℹ️  使用者 %s 沒有現有狀態需要清除", user_name)
        else:
            logger.warning("⚠️  無法從檔名識別使用者，無法執行狀態重設")
            sys.exit(1)

    try:
        analyzer = AttendanceAnalyzer(debug=args.debug)

        if incremental_mode:
            logger.info("📂 正在解析考勤檔案... (增量分析模式)")
        else:
            logger.info("📂 正在解析考勤檔案... (完整分析模式)")

        analyzer.parse_attendance_file(filepath, incremental=incremental_mode)

        logger.info("📝 正在分組記錄...")
        analyzer.group_records_by_day()

        logger.info("🔍 正在分析考勤...")
        analyzer.analyze_attendance()

        logger.info("📊 正在生成報告...")
        report = analyzer.generate_report()

        logger.info("\n")
        for line in report.split('\n'):
            logger.info(line)

        exported_files: list[str] = []
        backup_files: list[str] = []

        if format_type.lower() == 'csv':
            output_filepath = filepath.replace('.txt', '_analysis.csv')
            backup_path = analyzer.export_report(
                output_filepath, 'csv', export_policy=export_policy
            )
            exported_files.append(output_filepath)
            if backup_path:
                backup_files.append(backup_path)
            logger.info("✅ CSV報告已匯出: %s", output_filepath)
        else:
            output_filepath = filepath.replace('.txt', '_analysis.xlsx')
            backup_path = analyzer.export_report(
                output_filepath, 'excel', export_policy=export_policy
            )
            exported_files.append(output_filepath)
            if backup_path:
                backup_files.append(backup_path)
            logger.info("✅ Excel報告已匯出: %s", output_filepath)

        if format_type.lower() == 'excel':
            csv_filepath = filepath.replace('.txt', '_analysis.csv')
            backup_path = analyzer.export_report(
                csv_filepath, 'csv', export_policy=export_policy
            )
            exported_files.append(csv_filepath)
            if backup_path:
                backup_files.append(backup_path)
            logger.info("📝 同時匯出CSV格式: %s", csv_filepath)

        if cleanup_exports:
            from lib.export_cleanup import (
                cleanup_exports as cleanup_exports_helper,
                list_backups,
            )

            timestamp_candidates: set[str] = set()
            for path in exported_files:
                for candidate in list_backups(path):
                    timestamp_candidates.add(os.path.abspath(candidate))
            for backup in backup_files:
                if os.path.exists(backup):
                    timestamp_candidates.add(os.path.abspath(backup))

            canonical_candidates: set[str] = set()
            if args.debug:
                for path in exported_files:
                    if os.path.exists(path):
                        canonical_candidates.add(os.path.abspath(path))

            if not timestamp_candidates and not canonical_candidates:
                logger.info("ℹ️ 沒有可清除的匯出檔案")
            else:
                logger.info("🧹 可清除匯出檔案：")
                for candidate in sorted(timestamp_candidates):
                    logger.info("   - %s", os.path.basename(candidate))
                for candidate in sorted(canonical_candidates):
                    logger.info("   - %s (本次輸出)", os.path.basename(candidate))

                response = input("是否刪除上述檔案？[y/N]: ").strip().lower()
                if response not in {"y", "yes"}:
                    logger.info("ℹ️ 已取消匯出清理")
                else:
                    removed_paths: set[str] = set()
                    for path in exported_files:
                        removed = cleanup_exports_helper(
                            path, include_canonical=args.debug
                        )
                        removed_paths.update(os.path.abspath(p) for p in removed)
                    for backup in backup_files:
                        if os.path.exists(backup):
                            os.remove(backup)
                            removed_paths.add(os.path.abspath(backup))
                    if removed_paths:
                        removed_display = ', '.join(
                            sorted(os.path.basename(p) for p in removed_paths)
                        )
                        if args.debug:
                            logger.info("🧹 Debug 匯出檔案已清除: %s", removed_display)
                        else:
                            logger.info("🧹 已移除 timestamp 備份: %s", removed_display)
                    else:
                        logger.info("ℹ️ 沒有檔案被刪除")

    except Exception as e:
        logger.error("❌ 錯誤: %s", e)
        sys.exit(1)
