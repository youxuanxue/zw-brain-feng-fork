"""Live workbench backlog projection — 业务运营员（ROLE_BUSIAUDIT）工作台待办从真实库现算.

缺陷 2（0604 客户试用反馈）修复：业务运营员工作台「今日待办」此前要么为空、要么沿用
seed_snapshot.json 里 C-1 删演示单后**遗留的陈旧文案**（subtitle / aiSummary 仍提
「专区待纳入 / 能力包待审核」，但实际 todos 已空），且这些待办**点不动**（无深链）。

本模块把业务运营员的待办**从真实库的真实积压现算**，与 ``system.snapshot`` 的 J1 列表
enrich（``discovery_snapshot_projection``）同源同模式：DB 有积压则生成待办，每条**深链到
既有的可办理页面**（P5 提供方工作台 / 申请审批收件箱 / 异议收件箱），积压为 0 时
**不生成该条待办**（无空死链）。

业务运营员**真实职责**待办口径（0605 反馈 6.4#11 业务答复背书 + D53 方向裁决）：
审核（目录/资源审批）是**部门管理员**职责，业务运营员的工作重心是**发布 / 受理 / 汇总**。
此前把「待审核目录 / 待审核资源 / 待补全用途」放进业务运营员工作台属职责错配，本次纠正：
  - 待发布目录 = catalog_entry.lifecycle_status == 'approved_pending_publish'  → P5 提供方（发布卡）
  - 待发布资源 = resource_asset.lifecycle_status == 'approved_pending_publish' → P5 提供方
  - 待受理申请 = 申请单（kind=apply）status ∈ {submitted, under_review}        → 申请·审批·跟踪
  - 待受理异议 = objection_case.status == 'submitted'（待受理，未进入核查）       → 异议收件箱
  - 待汇总需求 = 需求登记（kind=demand）处于供方待汇总相位                       → 供需对接收件箱

一张 application_record 表混存「申请 / 需求登记 / 业务需求」三类（kind 存 payload_json），
故「待受理申请」必须按 kind=apply 过滤、「待汇总需求」走需求相位口径，两条口径不互串。

这不改任何角色/流程/状态机语义——只把**既有的真实积压**按业务运营员真实职责投影成
**可点的待办**，深链目标全是**已存在**的路由与收件箱（无新页面、无新流转）。
"""

from __future__ import annotations

import copy
from typing import Any

from zw_brain.domain.repositories.application import ApplicationRepository
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.domain.repositories.objection import ObjectionRepository
from zw_brain.domain.repositories.resource_api import ResourceApiRepository
from zw_brain.domain.repositories.supply_demand import SupplyDemandRepository
from zw_brain.domain.supply_demand_phase import (
    PHASE_MANUAL_REGISTERED,
    PHASE_RECOMMEND_FAILED,
    PHASE_REGISTERED,
)
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

# 业务运营员角色码（旧平台 7 角色码之一，D23）。
_BUSIAUDIT_ROLE = "ROLE_BUSIAUDIT"

# 待受理申请：提交后未终结、等待受理/审批的**申请单**态（kind=apply，不含需求登记）。
_APPLICATION_BACKLOG_STATUSES = frozenset({"submitted", "under_review"})

# 待汇总需求：需求登记进入供方侧、等待业务运营员汇总响应的相位（同 provider_snapshot 口径）。
_DEMAND_PROVIDER_PHASES = frozenset(
    {PHASE_REGISTERED, PHASE_MANUAL_REGISTERED, PHASE_RECOMMEND_FAILED}
)


def _count_pending_applications(application_repo: ApplicationRepository, tenant_id: str) -> int:
    """待受理申请 = kind=apply 且 status∈受理态的申请单数。

    application_record 表混存 申请/需求/业务需求三类（kind 存 payload_json），不按 kind 过滤会把
    登记需求误算进「待受理申请」。需求另归「待汇总需求」，两条口径互不串。
    """
    return sum(
        1
        for record in application_repo.list_records(tenant_id=tenant_id)
        if (record.payload_json or {}).get("kind", "apply") == "apply"
        and record.status in _APPLICATION_BACKLOG_STATUSES
    )


def _backlog_todos(tenant_id: str) -> list[dict[str, Any]]:
    """从真实库现算业务运营员待办；每条 = 一类有积压（count>0）的待办，深链到既有办理页。"""
    catalog_repo = CatalogRepository()
    resource_repo = ResourceApiRepository()
    application_repo = ApplicationRepository()
    objection_repo = ObjectionRepository()
    supply_repo = SupplyDemandRepository()

    pending_publish = catalog_repo.count_entries(
        tenant_id=tenant_id, lifecycle_status="approved_pending_publish"
    )
    pending_resource_publish = len(
        resource_repo.list_assets(tenant_id=tenant_id, lifecycle_status="approved_pending_publish")
    )
    pending_applications = _count_pending_applications(application_repo, tenant_id)
    pending_objections = len(objection_repo.list_cases(tenant_id=tenant_id, status="submitted"))
    pending_demands = sum(
        1
        for item in supply_repo.list_demands(tenant_id=tenant_id)
        if item.get("demand_phase") in _DEMAND_PROVIDER_PHASES
    )

    # (item_id, 文案前缀, count, 后缀状态, 深链, 行动句模板) — count==0 的不生成（无空死链）。
    # 行动句模板（G4，0605 反馈 6.4#10）：按类型给「N 条 X 待办」的自然动作分句，
    # 供 aiSummary 拼成「有 N 条申请待受理、M 条资源尚未发布，请尽快处理」式的分类型行动建议。
    candidates: list[tuple[str, str, int, str, str, str]] = [
        ("backlog-catalog-publish", "待发布目录", pending_publish, "待发布", "#/provider", "{n} 个目录待发布"),
        ("backlog-resource-publish", "待发布资源", pending_resource_publish, "待发布", "#/provider", "{n} 个资源待发布"),
        ("backlog-application", "待受理申请", pending_applications, "待受理", "#/request-flow", "{n} 条申请待受理"),
        (
            "backlog-objection",
            "待受理异议",
            pending_objections,
            "待受理",
            "#/provider/inbox/objection",
            "{n} 条异议待受理",
        ),
        (
            "backlog-demand",
            "待汇总需求",
            pending_demands,
            "待汇总",
            "#/provider/inbox/demand-match",
            "{n} 项需求待汇总",
        ),
    ]

    todos: list[dict[str, Any]] = []
    for item_id, label, count, status, href, action_tmpl in candidates:
        if count <= 0:
            continue
        todos.append(
            {
                "id": item_id,
                "title": f"{label} {count} 条",
                "status": status,
                "href": href,
                "category": "backlog",
                # G4：分类型行动分句（已带 count），aiSummary 据此拼分类型行动句。
                "action": action_tmpl.format(n=count),
            }
        )
    return todos


def enrich_workbench_backlog(
    view: dict[str, Any], role: str, *, tenant_id: str | None = None
) -> dict[str, Any]:
    """业务运营员工作台 todos 从真实库现算替换（其余角色原样返回）.

    与 ``discovery_snapshot_projection`` 同模式：**无条件以 DB 现算为准**——有积压给真实
    待办，零积压给诚实空列表（不回退陈旧 seed 文案）。subtitle/aiSummary 也据现算积压
    重写为诚实信号，消除 C-1 删演示单后遗留的陈旧引用。

    其它角色（部门操作员 / 部门管理员等）待办由 ``sync_request_todos`` 真投影、本身已是
    可点深链，不在此重算。
    """
    if role != _BUSIAUDIT_ROLE:
        return view
    tid = tenant_id or get_runtime_tenant_id()
    out = copy.deepcopy(view)
    todos = _backlog_todos(tid)
    out["todos"] = todos
    total = sum(int(t["title"].split()[1]) for t in todos) if todos else 0
    if todos:
        parts = "、".join(t["title"] for t in todos)
        out["subtitle"] = f"你有 {total} 条真实积压待办：{parts}。"
    else:
        out["subtitle"] = "当前没有待办积压。"
    # G4（0605 反馈 6.4#10）：办理建议从笼统总数改为**分类型行动句**——按真实积压类型给
    # 「有 N 条申请待受理、M 个资源待发布……，请尽快处理」的具体动作建议，而非「共 N 条积压」。
    # 各分句已带 count（单源 = _backlog_todos 的 action 字段），零积压给诚实空态。
    action_clauses = [str(t["action"]) for t in todos if t.get("action")]
    out["aiSummary"] = {
        "summary": (
            f"有{('、'.join(action_clauses))}，请尽快处理。"
            if action_clauses
            else "当前没有待办积压，发布与受理队列均已清空。"
        ),
        "actions": [t["title"] for t in todos],
        "basis": ["待办数据从真实库现算（目录/资源发布态 + 申请/异议受理态 + 需求汇总相位）"],
    }
    out["highlights"] = []
    return out
