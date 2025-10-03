"""Shared i18n helpers for fhr components."""

from __future__ import annotations

import gettext
import locale
import os
from collections.abc import Callable
from functools import cache, lru_cache

_DEFAULT_FALLBACKS = {
    "zh_TW": {
        "Wizard": "精靈",
        "Next": "下一步",
        "Back": "上一步",
        "Run": "執行",
        "Cancel": "取消",
        "Quit": "離開",
        "Welcome": "歡迎",
        "File": "檔案",
        "Recent": "最近",
        "Format": "格式",
        "Options": "選項",
        "Confirm & Run": "確認與執行",
        "Preview": "預覽",
        "Done": "完成",
        "Excel": "Excel",
        "CSV": "CSV",
        "Incremental": "增量模式",
        "Full Re-Analyze": "完整重跑",
        "Reset State": "重置狀態",
        "Output": "輸出",
        "Rows Previewed": "預覽列數",
        "Parsing attendance data": "解析考勤資料",
        "Grouping daily records": "整理每日紀錄",
        "Applying analysis rules": "套用規則分析",
        "Exporting reports": "匯出報表",
        "⏳ Waiting for analysis to start": "⏳ 等待分析開始",
        "🚀 Preparing analysis": "🚀 正在準備分析…",
        "✅ Analysis complete": "✅ 分析完成",
        "❌ Analysis failed": "❌ 分析失敗",
        "🛑 Analysis cancelled": "🛑 分析已取消",
        "🌐 Language switched to English": "🌐 已切換語系為 English",
        "🌐 Language switched to Traditional Chinese": "🌐 已切換語系為 繁體中文",
        "Traditional Chinese": "繁體中文",
        "English": "English",
    }
}


@lru_cache(maxsize=1)
def detect_language() -> str:
    env_lang = os.getenv("FHR_LANG")
    if env_lang:
        return env_lang
    try:
        lang, _ = locale.getdefaultlocale()  # type: ignore[assignment]
    except Exception:
        lang = None
    if lang and str(lang).lower().startswith("zh"):
        return "zh_TW"
    return "en"


@cache
def get_translator(language: str | None = None) -> Callable[[str], str]:
    lang = language or detect_language()
    try:
        translation = gettext.translation(
            "fhr", localedir="locales", languages=[lang], fallback=False
        )
        return translation.gettext  # type: ignore[return-value]
    except Exception:
        pass

    fallback_table: dict[str, str] = _DEFAULT_FALLBACKS.get(lang, {})

    def _(message_id: str) -> str:
        return fallback_table.get(message_id, message_id)

    return _
