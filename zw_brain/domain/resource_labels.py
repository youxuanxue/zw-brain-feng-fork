"""资源/目录共享枚举 → 中文 label 与 summary_json 解包助手（单一事实源）.

catalog_service（编制规范字段投影）与 typed_resource_detail（分型详情块）都要把旧平台
``update_cycle`` 枚举映成中文、都要剥 summary_json 的 ``summary`` 外层 wrapper。这些是
**确定性查表/解包**，不该各存一份手同步——收口到此，两边 import，消除同进程漂移。
"""
from __future__ import annotations

from typing import Any

# 业务/数据/资源更新周期码 → 中文（旧平台 dsp_catalog / data_resource update_cycle 枚举 1-9）。
UPDATE_CYCLE_LABELS: dict[str, str] = {
    "1": "实时",
    "2": "每日",
    "3": "每周",
    "4": "每月",
    "5": "每季度",
    "6": "每半年",
    "7": "每年",
    "8": "不定期",
    "9": "不更新",
}


def summary_body(summary: Any) -> dict[str, Any]:
    """剥 summary_json 外层 wrapper：有嵌套 ``summary`` 子 dict 则返回它，否则返回原 dict。

    非 dict 入参归一到空 dict（typed_resource_detail 的 summary 可能为 None/缺省）。
    """
    if not isinstance(summary, dict):
        return {}
    nested = summary.get("summary")
    return nested if isinstance(nested, dict) else summary
