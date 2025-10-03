from __future__ import annotations

import argparse
import sys

from .app import run_app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tui",
        description="啟動考勤分析 Textual 介面",
    )
    parser.add_argument(
        "--webview",
        action="store_true",
        help="使用 textual-web 於瀏覽器中開啟（需先安裝 textual-web）",
    )
    parser.add_argument(
        "--no-webview",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--dark",
        action="store_true",
        help="以深色主題啟動（預設）",
    )
    parser.add_argument(
        "--light",
        action="store_true",
        help="以淺色主題啟動",
    )

    args = parser.parse_args(argv)

    if args.webview and args.no_webview:
        parser.error("--webview 與 --no-webview 無法同時使用")

    dark: bool | None = None
    if args.dark and args.light:
        parser.error("--dark 與 --light 僅能擇一")
    if args.dark:
        dark = True
    elif args.light:
        dark = False

    run_app(webview=bool(args.webview and not args.no_webview), dark=dark)


if __name__ == "__main__":
    main(sys.argv[1:])
