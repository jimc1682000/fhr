"""Portal form-status lists, shared by portal-apply, cascade and week-hours.

Kept free of agent-browser imports so pure logic can use it.
"""

from __future__ import annotations

# 實際清單狀態與既有 Portal 狀態別名；未知狀態不可推定單據有效或失效。
ACTIVE_FORM_STATUSES = frozenset(
    {"未處理", "簽核中", "已核准", "主管簽核 - 一階主管", "流程結束(完成)"}
)
INACTIVE_FORM_STATUSES = frozenset({"已駁回", "退件", "已撤回", "流程結束(駁回)", "流程停止(抽單)"})
# The subset of ACTIVE_FORM_STATUSES that means the form went through.
FINAL_FORM_STATUSES = frozenset({"已核准", "流程結束(完成)"})

# Any status mentioning these is dead, whatever stage name surrounds it.
DEAD_STATUS_MARKERS = ("抽單", "駁回")


def normalize_status(status: str | None) -> str:
    """Strip, and turn full-width parentheses into ASCII ones."""
    return (status or "").strip().replace("（", "(").replace("）", ")")


def is_dead_status(status: str | None) -> bool:
    status = normalize_status(status)
    return status in INACTIVE_FORM_STATUSES or any(m in status for m in DEAD_STATUS_MARKERS)
