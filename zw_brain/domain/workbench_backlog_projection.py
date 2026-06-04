"""Live workbench backlog projection — 业务运营员（ROLE_BUSIAUDIT）工作台待办从真实库现算.

缺陷 2（0604 客户试用反馈）修复：业务运营员工作台「今日待办」此前要么为空、要么沿用
seed_snapshot.json 里 C-1 删演示单后**遗留的陈旧文案**（subtitle / aiSummary 仍提
「专区待纳入 / 能力包待审核」，但实际 todos 已空），且这些待办**点不动**（无深链）。

本模块把业务运营员的待办**从真实库的真实积压现算**，与 ``system.snapshot`` 的 J1 列表
enrich（``discovery_snapshot_projection``）同源同模式：DB 有积压则生成待办，每条**深链到
既有的可办理页面**（P5 提供方工作台 / 目录审核收件箱 / 申请审批收件箱），积压为 0 时
**不生成该条待办**（无空死链）。

业务运营员核心积压口径（与既有 P5 收件箱 / catalog.entry.query 过滤口径一致）：
  - 待发布目录 = catalog_entry.lifecycle_status == 'approved_pending_publish'  → P5 提供方（发布卡）
  - 待审核目录 = catalog_entry.lifecycle_status == 'pending_review'             → 目录审核收件箱
  - 待审核资源 = resource_asset.lifecycle_status == 'pending_review'            → P5 提供方
  - 待受理申请 = application_record.status ∈ {submitted, under_review}          → 申请·审批·跟踪

这不改任何角色/流程/状态机语义——只把**既有的真实积压**投影成**可点的待办**，
深链目标全是**已存在**的路由与收件箱（无新页面、无新流转）。
"""

from __future__ import annotations

import copy
from typing import Any

from zw_brain.domain.data_quality import is_dirty_purpose, purpose_from_payload
from zw_brain.domain.repositories.application import ApplicationRepository
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.domain.repositories.resource_api import ResourceApiRepository
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

# 业务运营员角色码（旧平台 7 角色码之一，D23）。
_BUSIAUDIT_ROLE = "ROLE_BUSIAUDIT"

# 待受理申请：提交后未终结、等待业务运营员受理/审批的申请态。
_APPLICATION_BACKLOG_STATUSES = ["submitted", "under_review"]


def _backlog_todos(tenant_id: str) -> list[dict[str, Any]]:
    """从真实库现算业务运营员待办；每条 = 一类有积压（count>0）的待办，深链到既有办理页。"""
    catalog_repo = CatalogRepository()
    resource_repo = ResourceApiRepository()
    application_repo = ApplicationRepository()

    pending_publish = catalog_repo.count_entries(
        tenant_id=tenant_id, lifecycle_status="approved_pending_publish"
    )
    pending_catalog_review = catalog_repo.count_entries(
        tenant_id=tenant_id, lifecycle_status="pending_review"
    )
    pending_resource_review = len(
        resource_repo.list_assets(tenant_id=tenant_id, lifecycle_status="pending_review")
    )
    pending_applications = application_repo.count_by_statuses(
        statuses=_APPLICATION_BACKLOG_STATUSES, tenant_id=tenant_id
    )
    # 待补全用途（数据质量）：脏用途申请单数。第四组「角色待办语义注册表」的数据质量类目
    # 下沉至此（机制单源 = 本投影；脏值口径 = data_quality 单源，与 J1 列表降级 /
    # 供方质量队列同源同算）。
    dirty_purpose = sum(
        1
        for record in application_repo.list_records(tenant_id=tenant_id)
        if is_dirty_purpose(purpose_from_payload(record.payload_json))
    )

    # (item_id, 文案前缀, count, 后缀状态, 深链) — count==0 的不生成（无空死链）。
    candidates: list[tuple[str, str, int, str, str]] = [
        ("backlog-catalog-publish", "待发布目录", pending_publish, "待发布", "#/provider"),
        (
            "backlog-catalog-review",
            "待审核目录",
            pending_catalog_review,
            "待审核",
            "#/provider/inbox/catalog-review",
        ),
        ("backlog-resource-review", "待审核资源", pending_resource_review, "待审核", "#/provider"),
        ("backlog-application", "待受理申请", pending_applications, "待受理", "#/request-flow"),
        ("backlog-purpose-quality", "待补全用途", dirty_purpose, "数据质量", "#/provider"),
    ]

    todos: list[dict[str, Any]] = []
    for item_id, label, count, status, href in candidates:
        if count <= 0:
            continue
        todos.append(
            {
                "id": item_id,
                "title": f"{label} {count} 条",
                "status": status,
                "href": href,
                "category": "backlog",
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
    # aiSummary 也据现算重写——清掉删演示单后遗留的「专区待纳入 / 能力包待审核」陈旧引用。
    out["aiSummary"] = {
        "summary": (
            f"当前共有 {total} 条真实积压待办，点击任一待办可直达对应办理页处理。"
            if todos
            else "当前没有待办积压，目录发布与资源审核队列均已清空。"
        ),
        "actions": [t["title"] for t in todos],
        "basis": ["待办数据从真实库现算（目录/资源生命周期态 + 申请受理态）"],
    }
    out["highlights"] = []
    return out
