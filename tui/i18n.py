import os
import locale
import gettext
from typing import Callable, Dict


def detect_language() -> str:
    lang = os.getenv('FHR_LANG')
    if lang:
        return lang
    loc = None
    try:
        loc = locale.getdefaultlocale()[0]  # type: ignore[index]
    except Exception:
        pass
    if loc and str(loc).lower().startswith('zh'):
        return 'zh_TW'
    return 'en'


def get_translator() -> Callable[[str], str]:
    lang = detect_language()

    # Try gettext catalogs if available
    try:
        trans = gettext.translation('fhr', localedir='locales', languages=[lang], fallback=True)
        _ = trans.gettext  # type: ignore[attr-defined]
        # Return gettext if catalogs exist; if fallback True and no catalogs, gettext returns msgid
        return _  # type: ignore[return-value]
    except Exception:
        pass

    # Minimal in-repo dictionary until gettext catalogs are provided.
    ZH_TW: Dict[str, str] = {
        'Wizard': '精靈',
        'Next': '下一步',
        'Back': '上一步',
        'Run': '執行',
        'Cancel': '取消',
        'Quit': '離開',
        'Welcome': '歡迎',
        'File': '檔案',
        'Recent': '最近',
        'Format': '格式',
        'Options': '選項',
        'Confirm & Run': '確認與執行',
        'Preview': '預覽',
        'Done': '完成',
        'Excel': 'Excel',
        'CSV': 'CSV',
        'Incremental': '增量模式',
        'Full Re-Analyze': '完整重跑',
        'Reset State': '重置狀態',
        'Output': '輸出',
        'Rows Previewed': '預覽列數',
    }

    table = ZH_TW if lang.startswith('zh') else {}

    def _(msgid: str) -> str:
        return table.get(msgid, msgid)

    return _
