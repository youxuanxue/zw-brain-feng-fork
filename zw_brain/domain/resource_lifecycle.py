"""资源 / 目录生命周期状态 → 中文展示态（R12 单一事实源）。

机器值 ``lifecycle_status`` 是唯一事实；中文是它的投影。一切**逻辑**（申请门控 /
默认发现过滤 / 同义反复抑制）只比对机器值（如 ``== "active"``），**绝不**比对中文展示词
——展示词随业务口径会变，比对它会让逻辑悄悄失真。

**前端零词表**：展示词由后端随记录一并下发（serializer 补 ``lifecycle_label`` 字段、
card 的 ``status`` 字段已是中文），前端只读不译，消除"两份词表手同步漂移"。

资源与目录共用此表（D53①：``active`` 对需求方语义 = **已发布**）。交付任务域里
``active`` = "进行中" 是**另一词域**（`zw-brain-web` ``REQUEST_STATUS_ZH``），井水不犯河水
——同一 slug 跨域不同义，正是"不能用一张全局表"的实证。
"""
from __future__ import annotations

from typing import Any

# D53①：active 对需求方 = 已发布（反转 D45 旧词"可复用"——需求方默认视图只见已发布、
# 该 chip 本就被同义反复抑制，真实观众是提供方 / 审核员，对其即"已发布"）。
_LIFECYCLE_LABEL = {
    "draft": "草稿",
    "pending_review": "审核中",
    "pending_platform_review": "平台审核中",
    "approved_pending_publish": "待发布",
    "active": "已发布",
    "retired": "已退役",
    "suspended": "已暂停",
    "expired": "已过期",
    "revoked": "已下线",
    "rejected": "已驳回",
}


def lifecycle_label(status: str | None) -> str:
    """生命周期机器值 → 中文展示态；未知值原样返回（诚实，不臆造）。"""
    return _LIFECYCLE_LABEL.get(str(status or ""), str(status or ""))


def with_lifecycle_label(payload: dict[str, Any]) -> dict[str, Any]:
    """给携带 ``lifecycle_status`` 的返回 dict 补 ``lifecycle_label`` 中文（就地、返回原 dict）。

    用于不经 serializer 的写动作返回（建草稿 / 状态流转），让前端零词表也能展示中文态。
    """
    if "lifecycle_status" in payload:
        payload["lifecycle_label"] = lifecycle_label(payload.get("lifecycle_status"))
    return payload
