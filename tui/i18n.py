import os
import locale
from typing import Callable


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
    # Placeholder translator: return msgid as-is; UI will provide Chinese
    # strings when language is zh_TW. For missing translations, fallback to
    # English (msgid) by design.
    def _(msgid: str) -> str:
        return msgid
    return _

