"""国家扩展要素编制状态机走查器（D50/C5，national-ext-elements 子旅程）。

**硬约束（D50 §三 + national-ext-elements.feature 场景4）**：本状态机与政务目录主线
（``catalog_entry`` / ``catalog_item``）**完全独立**——两套表、两套状态机，编制任务
绝不写入政务目录表。

编制生命周期态取真实「目录编制」页筛选枚举（old/20260519 目录管理-国家目录治理）：
  草稿 → 待业务部门审核 → 待主管部门审核 → 已发布；
  历史目录处理：已发布 →（变更）变更草稿 → 变更待业务部门审核 → 变更待主管部门审核 → 已发布；
               已发布 →（撤销）撤销待审核 → 已撤销。

2 级审核（业务部门 → 主管部门）**复用 approval_flow_walker.instantiate_steps_from_schema**：
本模块声明一个 ``national_ext_elem`` 串行 schema（start→业务部门审核→主管部门审核→end，
全 always 边），走查出有序 2 步——与 J1 自定义审批同一引擎、同一 happy-path 串行语义
（本期不做条件求值器，承 D49 不镀金）。审核推进的是编制任务自有 ``compile_status``，
不写 ApprovalCase（编制任务是独立聚合，审核步骤由本走查派生、由 handler 落任务态）。

发布动作 = 「同步国家平台」，经 C4 国家通道 gate 出站；未配置即诚实 pending（本模块只管
状态机，不接出站——出站在 handler 经 national_channel_gate）。
"""

from __future__ import annotations

from typing import Any

from zw_brain.domain.approval_flow_walker import instantiate_steps_from_schema

# 复用 approval-flow 引擎时的独立 schema 码（与 J1 baseline / 其它自定义 schema 隔离）。
FLOW_SCHEMA_CODE = "national_ext_elem"

# 编制生命周期态（单一事实源；字符串码对应真实「目录编制」页中文枚举）。
DRAFT = "draft"  # 草稿 / 待编制
PENDING_BUSINESS_REVIEW = "pending_business_review"  # 待业务部门审核
PENDING_SUPERVISOR_REVIEW = "pending_supervisor_review"  # 待主管部门审核
PUBLISHED = "published"  # 已发布
REVISION_DRAFT = "revision_draft"  # 变更草稿
PENDING_BUSINESS_REVIEW_REVISION = "pending_business_review_revision"  # 变更待业务部门审核
PENDING_SUPERVISOR_REVIEW_REVISION = "pending_supervisor_review_revision"  # 变更待主管部门审核
PENDING_REVOKE_REVIEW = "pending_revoke_review"  # 撤销待审核
REVOKED = "revoked"  # 已撤销

# 合法迁移（happy-path 含审核驳回回退；非法迁移由调用方 raise）。
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    DRAFT: {PENDING_BUSINESS_REVIEW},
    PENDING_BUSINESS_REVIEW: {PENDING_SUPERVISOR_REVIEW, DRAFT},  # 通过→主管 / 驳回→回草稿
    PENDING_SUPERVISOR_REVIEW: {PUBLISHED, PENDING_BUSINESS_REVIEW},  # 通过→发布 / 驳回→回业务
    PUBLISHED: {REVISION_DRAFT, PENDING_REVOKE_REVIEW},  # 历史目录处理：变更 / 撤销
    REVISION_DRAFT: {PENDING_BUSINESS_REVIEW_REVISION},
    PENDING_BUSINESS_REVIEW_REVISION: {PENDING_SUPERVISOR_REVIEW_REVISION, REVISION_DRAFT},
    PENDING_SUPERVISOR_REVIEW_REVISION: {PUBLISHED, PENDING_BUSINESS_REVIEW_REVISION},
    PENDING_REVOKE_REVIEW: {REVOKED, PUBLISHED},  # 撤销通过→已撤销 / 驳回→回已发布
    REVOKED: set(),
}

# 2 级审核串行 schema（业务部门 → 主管部门）。复用 approval_flow_walker 走查为有序步骤。
_REVIEW_SCHEMA_PAYLOAD: dict[str, Any] = {
    "nodes": [
        {"node_code": "start", "node_type": "start"},
        {"node_code": "business_dept", "node_type": "approval", "node_name": "业务部门审核"},
        {"node_code": "supervisor_dept", "node_type": "approval", "node_name": "主管部门审核"},
        {"node_code": "end", "node_type": "end"},
    ],
    "branches": [
        {"from_node_code": "start", "to_node_code": "business_dept", "condition_kind": "always"},
        {"from_node_code": "business_dept", "to_node_code": "supervisor_dept", "condition_kind": "always"},
        {"from_node_code": "supervisor_dept", "to_node_code": "end", "condition_kind": "always"},
    ],
}


class NationalExtElemTransitionError(ValueError):
    """非法编制态迁移；调用方 fail-closed（绝不静默落非法态）。"""


def is_terminal(status: str) -> bool:
    return not _ALLOWED_TRANSITIONS.get(status)


def validate_transition(from_status: str, to_status: str) -> None:
    """编制态迁移校验；非法 → raise（同 status 视为 no-op 合法）。"""
    if from_status == to_status:
        return
    allowed = _ALLOWED_TRANSITIONS.get(from_status)
    if allowed is None:
        raise NationalExtElemTransitionError(f"unknown compile status: {from_status!r}")
    if to_status not in allowed:
        raise NationalExtElemTransitionError(
            f"illegal compile transition: {from_status!r} → {to_status!r}; "
            f"allowed: {sorted(allowed) or '∅'}"
        )


def review_step_specs() -> list[dict[str, Any]]:
    """复用 approval_flow_walker 走查 national_ext_elem schema → 有序 2 步审核。

    返回 [业务部门审核, 主管部门审核] 的 step_spec（step_no 从 1 起）。
    """
    return instantiate_steps_from_schema(_REVIEW_SCHEMA_PAYLOAD)["steps"]


def submit_target(current: str) -> str:
    """提交送审目标态：草稿→待业务部门审核；变更草稿→变更待业务部门审核。"""
    table = {
        DRAFT: PENDING_BUSINESS_REVIEW,
        REVISION_DRAFT: PENDING_BUSINESS_REVIEW_REVISION,
    }
    if current not in table:
        raise NationalExtElemTransitionError(f"{current!r} 非可提交态")
    nxt = table[current]
    validate_transition(current, nxt)
    return nxt


def next_review_status(current: str, *, approve: bool) -> str:
    """审核决策 → 下一编制态（happy-path 串行；驳回回退上一态）。

    覆盖正式编制链与历史目录处理的变更链（两条链同构）。
    """
    table_approve = {
        PENDING_BUSINESS_REVIEW: PENDING_SUPERVISOR_REVIEW,
        PENDING_SUPERVISOR_REVIEW: PUBLISHED,
        PENDING_BUSINESS_REVIEW_REVISION: PENDING_SUPERVISOR_REVIEW_REVISION,
        PENDING_SUPERVISOR_REVIEW_REVISION: PUBLISHED,
        PENDING_REVOKE_REVIEW: REVOKED,
    }
    table_reject = {
        PENDING_BUSINESS_REVIEW: DRAFT,
        PENDING_SUPERVISOR_REVIEW: PENDING_BUSINESS_REVIEW,
        PENDING_BUSINESS_REVIEW_REVISION: REVISION_DRAFT,
        PENDING_SUPERVISOR_REVIEW_REVISION: PENDING_BUSINESS_REVIEW_REVISION,
        PENDING_REVOKE_REVIEW: PUBLISHED,
    }
    table = table_approve if approve else table_reject
    if current not in table:
        raise NationalExtElemTransitionError(f"{current!r} 非可审核态，无法决策")
    nxt = table[current]
    validate_transition(current, nxt)
    return nxt
