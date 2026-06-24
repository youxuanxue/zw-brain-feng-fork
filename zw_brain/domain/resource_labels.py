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

# 共享类型码 → 中文（旧平台 dc_resource_base_info / catalog summary 口径：
# 1=无条件共享、2=有条件共享、3=不予共享）。approval_flow_baseline.SHARED_TYPE 是审批流
# 另一码空间，禁止用于资源/目录卡片展示。
SHARE_TYPE_LABELS: dict[str, str] = {
    "1": "无条件共享",
    "2": "有条件共享",
    "3": "不予共享",
    "unconditional": "无条件共享",
    "conditional": "有条件共享",
    "closed": "不予共享",
}
SHARE_TYPE_UNCONDITIONAL = 1
SHARE_TYPE_CONDITIONAL = 2
SHARE_TYPE_CLOSED = 3

# 卡片视觉级别：后端下发，前端只按 class 渲染，不再自行翻译共享码。
SHARE_TYPE_LEVELS: dict[str, str] = {
    "无条件共享": "open",
    "有条件共享": "conditional",
    "不予共享": "closed",
}


def summary_body(summary: Any) -> dict[str, Any]:
    """剥 summary_json 外层 wrapper：有嵌套 ``summary`` 子 dict 则返回它，否则返回原 dict。

    非 dict 入参归一到空 dict（typed_resource_detail 的 summary 可能为 None/缺省）。
    """
    if not isinstance(summary, dict):
        return {}
    nested = summary.get("summary")
    return nested if isinstance(nested, dict) else summary


def share_type_from_mapping(data: Any) -> Any:
    """从旧/新字段名里取共享类型原始值，不做翻译。

    兼容 catalog summary（``shared_type``）与资源 access policy（``share_type`` /
    ``shareType``）。返回 None 表示缺失，调用方应诚实留空或按业务兜底。
    """
    if not isinstance(data, dict):
        return None
    for key in ("shared_type", "share_type", "sharedType", "shareType"):
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def share_type_int(raw: Any) -> int | None:
    """共享类型原始值 → 旧平台资源/目录码整数；无法识别返回 None。"""
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        key = str(raw).strip().lower()
        if key == "unconditional":
            return SHARE_TYPE_UNCONDITIONAL
        if key == "conditional":
            return SHARE_TYPE_CONDITIONAL
        if key in {"closed", "none", "no_share"}:
            return SHARE_TYPE_CLOSED
        return None


def share_type_label(raw: Any) -> str:
    """共享类型原始值 → 中文展示值；未知值原样转字符串，缺失返回空串。"""
    if raw in (None, ""):
        return ""
    key = str(raw).strip().lower()
    return SHARE_TYPE_LABELS.get(key, str(raw))


def share_type_level(label: Any) -> str:
    """共享类型中文展示值 → 卡片视觉级别。"""
    return SHARE_TYPE_LEVELS.get(str(label or ""), "")
