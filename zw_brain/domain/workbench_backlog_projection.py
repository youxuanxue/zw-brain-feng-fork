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
from zw_brain.domain.resource_kind import canonical_resource_kind
from zw_brain.domain.supply_demand_phase import (
    PHASE_MANUAL_REGISTERED,
    PHASE_RECOMMEND_FAILED,
    PHASE_REGISTERED,
)
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

# 业务运营员角色码（旧平台 7 角色码之一，D23）。
_BUSIAUDIT_ROLE = "ROLE_BUSIAUDIT"
# 部门管理员角色码。
_MANAGER_ROLE = "ROLE_ORGAN_MANAGER"

# D55/P10 部门管理员供数侧审核 stage：目录审核 = catalog_entry 处于部门待审 pending_review。
# G4（D55 查缺补漏）：照旧平台 v5「资源挂接审核 / 资源审核 = 部门管理员」校正后，挂接审核
# /provider/inbox/hookup-review 与服务注册审核（API 服务向导页行内）对部门管理员深链可达，
# 一并补投。反向编目审核 /provider/inbox/field-decision 仍归业务运营员（field-decision roles=
# [BUSIAUDIT]），MANAGER 深链不可达 → 不投（无空死链）。
_DEPT_REVIEW_STATUS = "pending_review"
# 物化资源挂接审核口径 = 非 API 类（含 kind 缺失脏行——审核是兜脏数据的环节，不藏行）；
# 服务注册审核口径 = API 类。canonical_resource_kind 折叠 legacy 值（service→api、folder→file），
# 与 provider_snapshot_projection 的收件箱分流同语义（同口径不串数）。
_API_CANONICAL_KIND = "api"

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


def _count_assets_pending_review(tenant_id: str, *, api_side: bool) -> int:
    """待审核资产数（lifecycle_status==pending_review），按 canonical kind 分流两条审核口径。

    api_side=True 数服务注册审核（canonical kind==api）；False 数挂接审核（其余，含 kind
    缺失脏行——藏行会让资产静默卡死在 pending_review）。两侧互斥不串数。
    """
    resource_repo = ResourceApiRepository()
    return sum(
        1
        for record in resource_repo.list_assets(
            tenant_id=tenant_id, lifecycle_status=_DEPT_REVIEW_STATUS
        )
        if (canonical_resource_kind(getattr(record, "resource_kind", None)) == _API_CANONICAL_KIND) is api_side
    )


def _manager_review_todos(tenant_id: str) -> list[dict[str, Any]]:
    """G4（D55 查缺补漏）：部门管理员供数侧审核 stage 待办（真实库现算，零积压不投，深链既有页）。

    照旧平台 v5「资源挂接审核 / 资源审核 = 部门管理员」校正后，部门管理员供数审核待办含三条
    （均深链 MANAGER 可达页，零积压不投，无空死链）：
      - 待审核目录 = catalog_entry.lifecycle_status==pending_review → /provider/inbox/catalog-review
      - 待审核挂接资源 = resource_asset(kind∈{table,file}).pending_review → /provider/inbox/hookup-review
      - 待审核服务 = resource_asset(kind∈{api,service}).pending_review → /provider/wizard/api-service（行内审核）
    反向编目审核 /provider/inbox/field-decision 仍归业务运营员（roles=[BUSIAUDIT]），MANAGER 深链
    不可达 → 不投。需求校核 / 目录撤销·变更·迁移审核本期无 MANAGER 可办理的 UI 收件箱 → 不投。
    """
    catalog_repo = CatalogRepository()
    pending_catalog_review = catalog_repo.count_entries(
        tenant_id=tenant_id, lifecycle_status=_DEPT_REVIEW_STATUS
    )
    pending_hookup_review = _count_assets_pending_review(tenant_id, api_side=False)
    pending_api_review = _count_assets_pending_review(tenant_id, api_side=True)
    candidates: list[tuple[str, str, int, str, str, str]] = [
        (
            "backlog-catalog-dept-review",
            "待审核目录",
            pending_catalog_review,
            "待审核",
            "#/provider/inbox/catalog-review",
            "{n} 个目录待部门审核",
        ),
        (
            "backlog-hookup-review",
            "待审核挂接资源",
            pending_hookup_review,
            "待审核",
            "#/provider/inbox/hookup-review",
            "{n} 个挂接资源待审核",
        ),
        (
            "backlog-api-review",
            "待审核服务",
            pending_api_review,
            "待审核",
            "#/provider/wizard/api-service",
            "{n} 个服务待审核",
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
                "action": action_tmpl.format(n=count),
            }
        )
    return todos


def _enrich_manager_backlog(view: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    """部门管理员（D55/P10·G4）：在既投部门审核待办上叠加供数侧审核待办（目录/挂接/服务审核）。

    保留 ``sync_request_todos`` 已投的 dept_approved 部门审核待办（可点深链），把现算的供数侧
    审核待办**前插**（去重 by id）。零积压不投供数审核待办（无空死链）。
    subtitle/aiSummary 同步重写为诚实信号（D57②/R-8：此前管理员一直漏出 seed 虚构
    「涉企采集准入待判定」叙事）。
    """
    out = copy.deepcopy(view)
    review_todos = _manager_review_todos(tenant_id)
    existing = out.get("todos") or []
    existing_ids = {t.get("id") for t in existing}
    prepended = [t for t in review_todos if t["id"] not in existing_ids]
    todos = prepended + existing
    out["todos"] = todos
    review_clauses = [str(t["action"]) for t in prepended if t.get("action")]
    other_count = len(existing)
    if other_count:
        review_clauses.append(f"{other_count} 条申请审批/汇总待办")
    _rewrite_advice(
        out,
        clauses=review_clauses,
        action_titles=[str(t.get("title", "")) for t in todos],
        empty_summary="当前没有审核待办积压。",
        basis="待办数据从真实库现算（目录/挂接资源/服务审核态 + 申请单审批态）",
    )
    return out


def _rewrite_advice(
    out: dict[str, Any],
    *,
    clauses: list[str],
    action_titles: list[str],
    empty_summary: str,
    basis: str,
) -> None:
    """subtitle / aiSummary / highlights 重写为真实库现算的诚实信号（D57②/R-8）。

    seed_snapshot.json 的工作台叙事（「停车场…黄金旅程」「绕开模板重复采集」等）是
    C-1 前的演示虚构文案，违 D11 精神——所有角色的办理建议一律从真实积压现算，
    零积压给诚实空态，不回退 seed 叙事。
    """
    if clauses:
        out["subtitle"] = f"你有 {len(action_titles)} 条待办：{'、'.join(clauses)}。"
        out["aiSummary"] = {
            "summary": f"有{('、'.join(clauses))}，请尽快处理。",
            "actions": [t for t in action_titles if t],
            "basis": [basis],
        }
    else:
        out["subtitle"] = empty_summary
        out["aiSummary"] = {"summary": empty_summary, "actions": [], "basis": [basis]}
    out["highlights"] = []


def _enrich_operator_backlog(view: dict[str, Any]) -> dict[str, Any]:
    """部门操作员（D57②/R-8）：维持「申请进度」形态（0609 docx 明文，拒协作待办）。

    todos 由 ``sync_request_todos`` 真投影、此处不动；只把 subtitle / 办理建议从 seed
    虚构叙事改为真实进度现算（分类型：申请在办 / 补录任务），零进度给诚实空态。
    """
    out = copy.deepcopy(view)
    todos = out.get("todos") or []
    progress = sum(1 for t in todos if str(t.get("category", "")) == "apply-progress")
    supplements = sum(1 for t in todos if str(t.get("category", "")).startswith("supplement"))
    other = len(todos) - progress - supplements
    clauses: list[str] = []
    if progress:
        clauses.append(f"{progress} 条申请在办")
    if supplements:
        clauses.append(f"{supplements} 项补录任务待完成")
    if other:
        clauses.append(f"{other} 项其他进度在跟踪")
    _rewrite_advice(
        out,
        clauses=clauses,
        action_titles=[str(t.get("title", "")) for t in todos],
        empty_summary="当前没有进行中的申请。",
        basis="申请进度从真实库现算（申请单状态 + 补录任务）",
    )
    return out


def _enrich_supervisor_view(view: dict[str, Any]) -> dict[str, Any]:
    """安全审计员（D57②/R-8）：纯只读监督岗（D55/P22「无任何写操作权限」）。

    工作台不投写动作待办（todos 恒空、不造监督仪表盘），办理建议改为诚实的只读监督
    指引——把人引向真正的监督面（查审计），替换 seed 虚构「绕开模板重复采集告警」叙事。
    P1Workbench.vue 同步把该角色从「申请人」误归类中拆出（监督概览语境）。
    """
    out = copy.deepcopy(view)
    out["todos"] = []
    out["subtitle"] = "安全审计员为纯只读监督岗，无办理待办。"
    out["aiSummary"] = {
        "summary": "如需开展监督核查，请前往「查审计」查看审计事件、证据回放与合规态势。",
        "actions": [],
        "basis": ["安全审计员收敛纯只读（D55/P22）：工作台不投写动作待办"],
    }
    out["highlights"] = []
    return out


def _enrich_ops_view(view: dict[str, Any]) -> dict[str, Any]:
    """平台运维员（D57②/R-8 核查）：工作台为运维核查语境，办理建议诚实现算。

    本期运维写待办（工单/巡检）无 UI 收件箱深链可达 → 不投（无空死链，同 G4 口径）；
    指引指向真实可达的运维面（服务调用监控 / 后台模块）。
    """
    out = copy.deepcopy(view)
    todos = out.get("todos") or []
    _rewrite_advice(
        out,
        clauses=[f"{len(todos)} 项运维事项待处理"] if todos else [],
        action_titles=[str(t.get("title", "")) for t in todos],
        empty_summary="当前没有运维待办积压。",
        basis="运维例行核查面：网关运行与服务调用统计见「服务调用监控」，外部系统/流程表单/身份治理见后台模块",
    )
    return out


def enrich_workbench_backlog(
    view: dict[str, Any], role: str, *, tenant_id: str | None = None
) -> dict[str, Any]:
    """工作台 todos / 办理建议从真实库现算，enrich 覆盖全部 5 角色（D57②/R-8）.

    与 ``discovery_snapshot_projection`` 同模式：**无条件以 DB 现算为准**——有积压给真实
    待办，零积压给诚实空列表（不回退陈旧 seed 文案）。subtitle/aiSummary 也据现算积压
    重写为诚实信号，消除 C-1 删演示单后遗留的虚构叙事（R-8）。

    - 业务运营员（ROLE_BUSIAUDIT）：todos **整体替换**为真实库积压（受理/发布/汇总，单一事实源）。
    - 部门管理员（ROLE_ORGAN_MANAGER）：在 ``sync_request_todos`` 已投的「部门审核待办（dept_approved）」
      之上**叠加供数侧审核待办**（目录 / 挂接资源 / 服务注册待部门审 pending_review，D55/P10·G4），
      零积压不投；办理建议重写。
    - 部门操作员（ROLE_ORGAN_OPERATER）：维持「申请进度」形态（0609 docx，拒协作待办），
      todos 由 sync 投影不动，办理建议从真实进度现算。
    - 安全审计员（ROLE_SECURITY_AUDIT）：纯只读监督岗，todos 恒空 + 只读监督指引。
    - 平台运维员（ROLE_SYSTEM）：运维核查语境，诚实空态/积压计数。
    """
    tid = tenant_id or get_runtime_tenant_id()
    if role == _MANAGER_ROLE:
        return _enrich_manager_backlog(view, tid)
    if role == "ROLE_ORGAN_OPERATER":
        return _enrich_operator_backlog(view)
    if role == "ROLE_SECURITY_AUDIT":
        return _enrich_supervisor_view(view)
    if role == "ROLE_SYSTEM":
        return _enrich_ops_view(view)
    if role != _BUSIAUDIT_ROLE:
        return view
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
