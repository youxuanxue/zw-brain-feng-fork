"""J2 供数侧生命周期脊柱（目录/资源「卡在谁桌上」竖向 stepper 单一事实源）。

承 J1 申请脊柱范式（``RequestService.status_timeline``）：读侧现算、单调、holder 只挂当前段、
取不到诚实留空绝不捏造。本模块给目录/资源生命周期算同形 timeline，供 ``provider_snapshot_
projection`` enrich 到供数方目录/资源卡，前端 ``PhaseTrack`` 渲染（不在前端重派生）。

机器值 ``lifecycle_status`` 是唯一事实；中文是它的投影（与 ``resource_lifecycle`` 同口径）。
段标签描述「该段自身」状态，不把整单 status 泄漏到已过去的段。

holder 取真实角色门（policy.py 各 ``*.execute`` 集合）的中文显示名（role_codes）：
- 目录：草稿=部门操作员（编制）/ 部门审核=部门管理员 / 平台审核=业务运营员 / 待发布=业务运营员
  （catalog.entry.review MANAGER→平台档、BUSIAUDIT→待发布；catalog.entry.publish=BUSIAUDIT）
- 资源：草稿=部门操作员（挂接）/ 挂接审核=部门管理员 / 待发布=业务运营员
  （resource.asset.review=MANAGER；resource.asset.publish=BUSIAUDIT）

终态（已发布/已退役等）无当前段、无 holder。非生命周期词汇（未知机器值）→ 不渲染 stepper。
"""
from __future__ import annotations

from typing import Any

from zw_brain.domain.resource_lifecycle import lifecycle_label

# 目录生命周期 5 段（草稿→部门审核→平台审核→待发布→已发布）。每段 = (stage 名, 段标签, holder)。
# pointer = 当前所处段序号（1-based）；status→pointer 见 _CATALOG_POINTER。
_CATALOG_STAGES: tuple[tuple[str, str, str], ...] = (
    ("草稿", "编制草稿", "部门操作员（编制）"),
    ("部门审核", "待部门审核", "部门管理员（部门审核）"),
    ("平台审核", "待平台审核", "业务运营员（平台审核）"),
    ("待发布", "待发布", "业务运营员（发布）"),
    ("已发布", "已发布", ""),
)
_CATALOG_POINTER: dict[str, int] = {
    "draft": 1,
    "pending_review": 2,
    "pending_platform_review": 3,
    "approved_pending_publish": 4,
    "active": 5,
}

# 资源生命周期 4 段（草稿→挂接审核→待发布→已发布）——无平台审核档。
_RESOURCE_STAGES: tuple[tuple[str, str, str], ...] = (
    ("草稿", "挂接草稿", "部门操作员（挂接）"),
    ("挂接审核", "待挂接审核", "部门管理员（挂接审核）"),
    ("待发布", "待发布", "业务运营员（发布）"),
    ("已发布", "已发布", ""),
)
_RESOURCE_POINTER: dict[str, int] = {
    "draft": 1,
    "pending_review": 2,
    "approved_pending_publish": 3,
    "active": 4,
}

# 驳回/退役等支线态：不进单调 stepper（无「下一段」语义），由 status_note / 生命周期标签诚实呈现。
_SIDELINE_STATES = frozenset({"rejected", "retired", "suspended", "expired", "revoked"})


def _build(
    status: str,
    stages: tuple[tuple[str, str, str], ...],
    pointer_map: dict[str, int],
) -> list[dict[str, Any]]:
    ptr = pointer_map.get(status)
    if ptr is None:
        return []  # 支线态 / 未知机器值 → 不渲染 stepper（诚实，不臆造进度）
    steps: list[dict[str, Any]] = []
    for i, (stage, label, holder) in enumerate(stages, start=1):
        seg = "done" if ptr > i else ("current" if ptr == i else "pending")
        # 已过段收口为该段名（如「部门审核」，不再显示「待部门审核」待办词）；当前/未来段给
        # 该段进行时/待办标签。段标签描述「该段自身」状态，不把整单 status 泄漏到已过去的段。
        steps.append(
            {
                "stage": stage,
                "status": seg,
                "label": stage if seg == "done" else label,
                # holder 只挂当前段（在谁桌上）；终态当前段 holder 本就空。
                "holder": holder if seg == "current" else "",
            }
        )
    return steps


def catalog_lifecycle_timeline(lifecycle_status: str | None) -> list[dict[str, Any]]:
    """目录生命周期 timeline（草稿→部门审核→平台审核→待发布→已发布）。

    支线态（已驳回/已退役…）返回空列表（不渲染 stepper，由生命周期标签诚实呈现）。
    """
    return _build(str(lifecycle_status or ""), _CATALOG_STAGES, _CATALOG_POINTER)


def resource_lifecycle_timeline(lifecycle_status: str | None) -> list[dict[str, Any]]:
    """资源生命周期 timeline（草稿→挂接审核→待发布→已发布）。"""
    return _build(str(lifecycle_status or ""), _RESOURCE_STAGES, _RESOURCE_POINTER)


def lifecycle_sideline_note(lifecycle_status: str | None) -> str:
    """支线态（驳回/退役…）的中文标注——供「无 stepper」时诚实说明当前态；非支线返回空。"""
    status = str(lifecycle_status or "")
    return lifecycle_label(status) if status in _SIDELINE_STATES else ""


# ── 异议线脊柱（G）─────────────────────────────────────────────────────────
# 异议 9 态机（ObjectionRepository.TRANSITIONS）折叠成单调 5 段办理脊柱：
#   提交 → 受理 → 核查 → 办结 → 归档（5 段；归档为终态）。
# 核查段细分（平台核查 / 部门核查）由当前 status 决定段标签 + holder；escalate 是事件式
# 督办（不改 status，见 _escalate_objection_case / list_supervised_cases）——脊柱不另设段、
# 也无 "escalated" status 入口（D57：升级是 add_process 事件而非状态迁移，无任何路径产出
# objection case status=="escalated"，故此处不为它建分支）。rejected 是支线终态（无 stepper，给 note）。
_OBJECTION_STAGES: tuple[str, ...] = ("提交", "受理", "核查", "办结", "归档")
# status → 当前段序号（1 提交 / 2 受理 / 3 核查 / 4 办结 / 5 归档）。
_OBJECTION_POINTER: dict[str, int] = {
    "submitted": 1,
    "accepted": 2,
    "platform_investigating": 3,
    "provider_investigating": 3,
    "resolved": 4,
    "closed": 5,
}
# 各 status 当前段的细分标签（核查段两态分流）+ holder（取真实角色门，缺则诚实留空不捏造）。
_OBJECTION_CURRENT: dict[str, tuple[str, str]] = {
    # status: (当前段标签, holder)
    "submitted": ("待受理", "业务运营员（受理）"),
    "accepted": ("已受理·待核查", "业务运营员（核查）"),
    "platform_investigating": ("平台核查中", "业务运营员（核查）"),
    "provider_investigating": ("部门核查中", "部门管理员（部门核查）"),
    "resolved": ("已办结·待确认", "申请方（确认/评价）"),
    "closed": ("已归档", ""),
}
_OBJECTION_REJECTED = "rejected"


def objection_timeline(status: str | None) -> list[dict[str, Any]]:
    """异议办理脊柱（提交→受理→核查→办结→归档），单调现算、holder 只挂当前段。

    rejected（驳回）= 支线终态：返回空列表（不渲染 stepper，由 status 标签诚实呈现）。
    未知 status 同样返回空（不臆造进度）。
    """
    s = str(status or "")
    ptr = _OBJECTION_POINTER.get(s)
    if ptr is None:
        return []  # rejected / 未知 → 无脊柱
    cur_label, cur_holder = _OBJECTION_CURRENT.get(s, ("", ""))
    steps: list[dict[str, Any]] = []
    for i, stage in enumerate(_OBJECTION_STAGES, start=1):
        seg = "done" if ptr > i else ("current" if ptr == i else "pending")
        if seg == "current":
            label, holder = cur_label or stage, cur_holder
        elif seg == "done":
            label, holder = stage, ""
        else:
            label, holder = stage, ""
        steps.append({"stage": stage, "status": seg, "label": label, "holder": holder})
    return steps


def objection_sideline_note(status: str | None) -> str:
    """异议支线态（驳回）的中文标注——供「无 stepper」时诚实说明；非支线返回空。"""
    return "已驳回" if str(status or "") == _OBJECTION_REJECTED else ""
