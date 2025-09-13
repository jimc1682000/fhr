import os
import locale
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

    # Minimal in-repo dictionary until gettext catalogs are provided.
    # msgid uses English; zh_TW provides Chinese text. Unmapped keys
    # fall back to msgid.
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
