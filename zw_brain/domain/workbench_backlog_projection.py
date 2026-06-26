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

M5 行内决策（供数侧待办彻底行内）：把 7 类**聚合计数**待办 re-grain 成携带
``action.kind=="decision-list"`` 的**行内载荷**——除了 count 头条（``title``=「待发布资源 4 条」、
``href`` 兜底深链、``actionClause`` 供 aiSummary 分句）外，再**逐条枚举**真实积压实体
（不止计数），每条带可办决策（发布/审核通过·驳回/异议受理），前端 count-row → 展开 →
逐条行内办理（直接打 capability，无需跳页）。能力/门禁与各 CTA 页严格一致：
  - 待发布目录/资源 → catalog.entry.publish / resource.asset.publish（发布）
  - 待平台审核目录 / 待审核目录 → catalog.entry.review（通过 approve / 驳回 reject+理由）
  - 待审核挂接资源 → resource.asset.review（通过 approve / 驳回 return_for_fix+理由）
  - 待审核反向编目草稿 → catalog.entry.reverse_draft.confirm / .reject（通过 / 驳回+理由）
  - 待受理异议 → objection.case.accept（受理）
督办（多步）/ 需求汇总（多步）/ 服务审核（向导）三类仍保 count + href 兜底（不 re-grain）。
MANAGER 三类审核待办枚举时**仍套 M8 visible_org_codes 行级过滤**（不把越界实体漏进行内列表）。
"""

from __future__ import annotations

import copy
from typing import Any

from zw_brain.domain.discovery_snapshot_projection import (
    request_party_in_scope,
    request_provider_in_scope,
    resource_owner_org_by_id,
)
from zw_brain.domain.models import (
    CatalogEntryRecord,
    ObjectionCaseRecord,
    ResourceAssetRecord,
)
from zw_brain.domain.objection_case_queues import project_pending_objection_cases
from zw_brain.domain.repositories.application import ApplicationRepository
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.domain.repositories.objection import ObjectionRepository
from zw_brain.domain.repositories.resource_api import ResourceApiRepository
from zw_brain.domain.repositories.supply_demand import SupplyDemandRepository
from zw_brain.domain.resource_kind import canonical_resource_kind
from zw_brain.domain.services.reference_service import ReferenceService
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
# 一并补投。D57⑧：反向编目审核改两级管线后，部门审（draft 阶段 confirm/reject）归部门
# 管理员（field-decision roles=[MANAGER]）→ MANAGER 补投「待审核反向编目草稿」；平台审
# （pending_platform_review）归业务运营员 → BUSIAUDIT 补投「待平台审核目录」，两级各自入账。
_DEPT_REVIEW_STATUS = "pending_review"
# 平台审档（正向编制部门审通过 + 反向编目部门审通过共用一个队列态，D57⑧ 汇入正向管线）。
_PLATFORM_REVIEW_STATUS = "pending_platform_review"
# 物化资源挂接审核口径 = 非 API 类（含 kind 缺失脏行——审核是兜脏数据的环节，不藏行）；
# 服务注册审核口径 = API 类。canonical_resource_kind 折叠 legacy 值（service→api、folder→file），
# 与 provider_snapshot_projection 的收件箱分流同语义（同口径不串数）。
_API_CANONICAL_KIND = "api"

# 待受理申请：提交后未终结、等待受理/审批的**申请单**态（kind=apply，不含需求登记）。
_APPLICATION_BACKLOG_STATUSES = frozenset({"submitted", "under_review"})
_NATIONAL_ESCALATE_STATUS = "dept_approved"

# 待汇总需求：需求登记进入供方侧、等待业务运营员汇总响应的相位（同 provider_snapshot 口径）。
_DEMAND_PROVIDER_PHASES = frozenset(
    {PHASE_REGISTERED, PHASE_MANUAL_REGISTERED, PHASE_RECOMMEND_FAILED}
)

# 部门隔离「第七面」（#294/#296 同类遗漏补口）：sync_request_todos 平行路径按角色逐条投的
# **申请待办**（id=payload['id'] 即 request_id），#294 只收口了快照 requests/approvals 面，
# 这条平行路径整条漏。读时（per-caller）按本机构可见域收口——谓词单一事实源
# request_party_in_scope（applicant∨provider∈visible；None=全量 / 空集=fail-closed），
# 与快照 requests/approvals/delivery 面同源，不在工作台层重复实现：
#   MANAGER 申请审核/汇总待办（办别人的单，category review/summary）；
#   OPERATER 申请进度/补录待办（category apply-progress/supplement-*）。
# 二者皆按 owner/applicant 机构收口（D61 裁决②；裁决③「我的申请按个人」由 requests 面 mine
# 标记承载，与 #294 一致——当前 actor 为 role 级身份[user:gov:<role>:*]，按个人 drop 在跨部门
# 操作员间无隔离效果，dept-scope 才真隔离；per-person 收敛属 IAM 身份补全后另立，见 actor 身份债）。
# BUSIAUDIT 受理待办（category=accept）保持全局（D61 裁决④），不在此收口集内。
_MANAGER_REVIEW_REQUEST_CATEGORIES = frozenset({"review"})
_MANAGER_SUMMARY_REQUEST_CATEGORIES = frozenset({"summary"})
_MANAGER_REQUEST_CATEGORIES = frozenset(
    _MANAGER_REVIEW_REQUEST_CATEGORIES | _MANAGER_SUMMARY_REQUEST_CATEGORIES
)
_OPERATER_REQUEST_CATEGORIES = frozenset(
    {"apply-progress", "supplement-township", "supplement-village"}
)


def _org_visible_request_ids(
    tenant_id: str, visible_org_codes: set[str] | None, *, caller_actor: str | None = None
) -> set[str]:
    """一次扫 application_record，现算本机构可见域内的 request-id 集合（payload['id'] 口径同
    sync_request_todos）。谓词单一事实源 request_party_in_scope（None=全量、空集=空、
    否则本机构可见域），与快照 requests 面同源、不在工作台层重复实现。

    ``caller_actor`` 非空时并入「我的申请按个人」逃生口（D61③，同 requests 面）：本人提的单
    （payload['applicant']==caller_actor）恒进集合、不被部门 org 过滤丢弃——仅部门操作员申请
    进度路径传入（管理员审核待办是供方 org-scope、不传，本人申请归其「我的申请」非审核待办）；
    空集 fail-closed 时连 mine 也不放行（保 D61 空集防御语义，同 requests 面）。"""
    fail_closed = visible_org_codes is not None and not visible_org_codes
    # 共享一个 ReferenceService（带 resolve memo）逐行过滤，消 per-record N+1（同 requests 面）。
    scope_ref = ReferenceService()
    visible: set[str] = set()
    for record in ApplicationRepository().list_records(tenant_id=tenant_id):
        payload = record.payload_json or {}
        rid = str(payload.get("id") or "")
        if not rid:
            continue
        if request_party_in_scope(record, visible_org_codes, tenant_id=tenant_id, ref=scope_ref):
            visible.add(rid)
        elif caller_actor and not fail_closed and str(payload.get("applicant") or "") == str(caller_actor):
            visible.add(rid)
    return visible


def _org_provider_visible_request_ids(tenant_id: str, visible_org_codes: set[str] | None) -> set[str]:
    """现算部门管理员可审核的 request-id 集合：仅 provider/资源归属方在可见域内才保留。"""
    scope_ref = ReferenceService()
    owner_map = resource_owner_org_by_id(tenant_id)
    visible: set[str] = set()
    for record in ApplicationRepository().list_records(tenant_id=tenant_id):
        payload = record.payload_json or {}
        rid = str(payload.get("id") or "")
        if not rid:
            continue
        if request_provider_in_scope(
            record,
            visible_org_codes,
            tenant_id=tenant_id,
            ref=scope_ref,
            resource_owner_by_id=owner_map,
        ):
            visible.add(rid)
    return visible


def _actor_visible_request_ids(
    tenant_id: str, visible_org_codes: set[str] | None, *, caller_actor: str | None
) -> set[str]:
    """Request ids owned by the current actor for operator progress cards.

    Live operator workbench cards deep-link to "我的申请", so their counts must
    use the same personal ownership scope. Tests and offline callers that do not
    carry an actor keep the historical org/global projection behavior.
    """
    if caller_actor is None:
        return _org_visible_request_ids(tenant_id, visible_org_codes)
    if visible_org_codes is not None and not visible_org_codes:
        return set()
    actor = str(caller_actor or "").strip()
    if not actor:
        return set()
    visible: set[str] = set()
    for record in ApplicationRepository().list_records(tenant_id=tenant_id):
        payload = record.payload_json or {}
        rid = str(payload.get("id") or "")
        if rid and str(payload.get("applicant") or "") == actor:
            visible.add(rid)
    return visible


def _drop_unscoped_request_todos(
    todos: list[dict[str, Any]], *, categories: frozenset[str], scoped_ids: set[str]
) -> list[dict[str, Any]]:
    """剔除越界的申请待办：category 命中收口集且 id(=request_id) 不在可见集 → drop.

    非申请待办（category 不在收口集，如供数侧 prepend 的 backlog-* 审核待办）原样放行。"""
    return [
        t
        for t in todos
        if str(t.get("category", "")) not in categories
        or str(t.get("id", "")) in scoped_ids
    ]


# ── M5 行内决策载荷构造（contract: action.kind=="decision-list"）───────────────
# 每个 item = 一个真实积压实体（枚举非计数）：id/label 给前端展示，capability/gate 为
# 默认能力门、basePayload 携实体码，decisions 逐项给可办决策（payload 合并到 basePayload，
# capability/gate 可逐决策覆盖，needsReason+reasonKey 标记驳回须填理由）。能力/门禁与各
# CTA 页严格一致（见模块 docstring）；前端 count-row 展开后逐条行内打 capability。


def _decision_list_action(items: list[dict[str, Any]]) -> dict[str, Any]:
    """构造 ``action.kind=="decision-list"`` 行内载荷（contract 锁定形状）。

    ``items`` 为逐实体决策项列表；空列表理论上不会到这里（零积压不投待办），
    但容错返回空 items 的合法结构（前端展开即空、不崩）。
    """
    return {"kind": "decision-list", "items": items}


def _ctx_row(label: str, value: Any) -> dict[str, str] | None:
    """一行 context 元组（label/value）；value 为空（None/空串）则返回 None 由调用方跳过。"""
    text = str(value).strip() if value is not None else ""
    if not text:
        return None
    return {"label": label, "value": text}


def _context(*rows: dict[str, str] | None) -> list[dict[str, str]]:
    """汇拢非空 context 行（≤3 行由调用方控制；此处只过滤 None/空）。"""
    return [row for row in rows if row]


def _publish_decision() -> list[dict[str, Any]]:
    """发布类单决策：发布（primary，无附加 payload，门禁=item.capability）。"""
    return [{"label": "发布", "tone": "primary", "success": "已发布", "payload": {}}]


def _review_decisions() -> list[dict[str, Any]]:
    """目录审核双决策：通过（approve）/ 驳回（reject，须填理由 reason）。"""
    return [
        {"label": "通过", "tone": "primary", "success": "已通过", "payload": {"decision": "approve"}},
        {
            "label": "驳回",
            "tone": "danger",
            "success": "已驳回",
            "payload": {"decision": "reject"},
            "needsReason": True,
            "reasonKey": "reason",
        },
    ]


def _hookup_review_decisions() -> list[dict[str, Any]]:
    """挂接资源审核双决策：通过（approve）/ 驳回（return_for_fix，须填理由 reason）。"""
    return [
        {"label": "通过", "tone": "primary", "success": "已通过", "payload": {"decision": "approve"}},
        {
            "label": "驳回",
            "tone": "danger",
            "success": "已驳回",
            "payload": {"decision": "return_for_fix"},
            "needsReason": True,
            "reasonKey": "reason",
        },
    ]


def _reverse_draft_decisions() -> list[dict[str, Any]]:
    """反向编目草稿审核双决策：通过 / 驳回——能力逐决策覆盖到 reverse_draft 专用门
    （confirm / reject），与正向 catalog.entry.review 区分（D57⑧ 两级管线第一级部门审）。
    驳回理由键=reject_reason（与 reverse_draft.reject handler 入参一致）。
    """
    return [
        {
            "label": "通过",
            "tone": "primary",
            "success": "已通过",
            "payload": {},
            "capability": "catalog.entry.reverse_draft.confirm",
            "gate": "catalog.entry.reverse_draft.confirm",
        },
        {
            "label": "驳回",
            "tone": "danger",
            "success": "已驳回",
            "payload": {},
            "capability": "catalog.entry.reverse_draft.reject",
            "gate": "catalog.entry.reverse_draft.reject",
            "needsReason": True,
            "reasonKey": "reject_reason",
        },
    ]


def _catalog_publish_item(entry: CatalogEntryRecord) -> dict[str, Any]:
    """待发布目录行内项：发布（catalog.entry.publish，basePayload.catalog_code）。"""
    return {
        "id": entry.catalog_code,
        "label": entry.title or entry.catalog_code,
        "context": _context(_ctx_row("目录", entry.title or entry.catalog_code)),
        "capability": "catalog.entry.publish",
        "gate": "catalog.entry.publish",
        "basePayload": {"catalog_code": entry.catalog_code},
        "decisions": _publish_decision(),
    }


def _resource_publish_item(asset: ResourceAssetRecord) -> dict[str, Any]:
    """待发布资源行内项：发布（resource.asset.publish，basePayload.resource_code）。"""
    return {
        "id": asset.resource_code,
        "label": asset.title or asset.resource_code,
        "context": _context(_ctx_row("资源", asset.title or asset.resource_code)),
        "capability": "resource.asset.publish",
        "gate": "resource.asset.publish",
        "basePayload": {"resource_code": asset.resource_code},
        "decisions": _publish_decision(),
    }


def _catalog_review_item(entry: CatalogEntryRecord) -> dict[str, Any]:
    """目录审核行内项（平台审 / 部门审共用）：通过·驳回（catalog.entry.review）。"""
    return {
        "id": entry.catalog_code,
        "label": entry.title or entry.catalog_code,
        "context": _context(_ctx_row("目录", entry.title or entry.catalog_code)),
        "capability": "catalog.entry.review",
        "gate": "catalog.entry.review",
        "basePayload": {"catalog_code": entry.catalog_code},
        "decisions": _review_decisions(),
    }


def _hookup_review_item(asset: ResourceAssetRecord) -> dict[str, Any]:
    """挂接资源审核行内项：通过·驳回（resource.asset.review）。"""
    return {
        "id": asset.resource_code,
        "label": asset.title or asset.resource_code,
        "context": _context(_ctx_row("资源", asset.title or asset.resource_code)),
        "capability": "resource.asset.review",
        "gate": "resource.asset.review",
        "basePayload": {"resource_code": asset.resource_code},
        "decisions": _hookup_review_decisions(),
    }


def _reverse_draft_review_item(entry: CatalogEntryRecord) -> dict[str, Any]:
    """反向编目草稿审核行内项：item 级能力取 confirm（默认门），决策逐项覆盖 confirm/reject。"""
    return {
        "id": entry.catalog_code,
        "label": entry.title or entry.catalog_code,
        "context": _context(_ctx_row("目录", entry.title or entry.catalog_code)),
        "capability": "catalog.entry.reverse_draft.confirm",
        "gate": "catalog.entry.reverse_draft.confirm",
        "basePayload": {"catalog_code": entry.catalog_code},
        "decisions": _reverse_draft_decisions(),
    }


def _objection_item(case: ObjectionCaseRecord) -> dict[str, Any]:
    """待受理异议行内项：受理（objection.case.accept，basePayload.objection_id）。

    context 取 case 暴露字段：责任单位（provider_org_id）+ 事项（target_type:target_id），
    缺失字段由 ``_ctx_row`` 跳过（诚实留白，不造空行）。
    """
    target = ""
    if case.target_id:
        target = f"{case.target_type}:{case.target_id}" if case.target_type else str(case.target_id)
    return {
        "id": case.id,
        "label": case.title or case.id,
        "context": _context(
            _ctx_row("责任单位", case.provider_org_id),
            _ctx_row("事项", target),
        ),
        "capability": "objection.case.accept",
        "gate": "objection.case.accept",
        "basePayload": {"objection_id": case.id},
        "decisions": [
            {"label": "受理", "tone": "primary", "success": "已受理", "payload": {}}
        ],
    }


def _national_escalate_item(record: Any) -> dict[str, Any]:
    """国家通道待转报行内项：转报（application.escalate_national）。

    队列口径 = channel_class=national 且主状态仍为 dept_approved；点击后由国家通道 gate
    决定真实出站或诚实 pending，不改 J1 主状态机。
    """
    payload = record.payload_json or {}
    request_id = str(payload.get("id") or "")
    resource_name = str(payload.get("resourceName") or payload.get("resource_name") or request_id)
    return {
        "id": request_id,
        "label": resource_name or request_id,
        "context": _context(
            _ctx_row("申请编号", request_id),
            _ctx_row("申请资源", resource_name),
            _ctx_row("申请部门", payload.get("applicantDept") or payload.get("applicant_dept")),
            _ctx_row("用途", payload.get("purpose")),
        ),
        "capability": "application.escalate_national",
        "gate": "application.escalate_national",
        "basePayload": {"application_code": request_id},
        "decisions": [
            {
                "label": "转报国家平台",
                "tone": "primary",
                "success": "已提交国家通道",
                "payload": {"action": "escalate"},
            }
        ],
    }


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


def _national_escalate_records(application_repo: ApplicationRepository, tenant_id: str) -> list[Any]:
    """国家级数据申请待转报 = kind=apply ∩ status=dept_approved ∩ channel_class=national."""
    return [
        record
        for record in application_repo.list_records(tenant_id=tenant_id)
        if (record.payload_json or {}).get("kind", "apply") == "apply"
        and record.status == _NATIONAL_ESCALATE_STATUS
        and str((record.payload_json or {}).get("channel_class") or "internal") == "national"
        and str((record.payload_json or {}).get("id") or "")
    ]


def _emit_backlog_todo(
    *,
    item_id: str,
    label: str,
    count: int,
    status: str,
    href: str,
    action_clause: str,
    action: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """构造一条 count 头条待办（count<=0 返回 None，零积压不投）；M5 行内项挂 ``action``。

    ``title`` 仍是计数头条（「待发布资源 4 条」）、``href`` 兜底深链、``actionClause`` 供
    aiSummary 分句（原 ``action`` 字符串字段更名 actionClause，腾出 ``action`` 给 decision-list
    dict）。``action`` 非空时为 :func:`_decision_list_action` 产物，前端 count-row 展开逐条办理。
    """
    if count <= 0:
        return None
    todo: dict[str, Any] = {
        "id": item_id,
        "title": f"{label} {count} 条",
        "status": status,
        "href": href,
        "category": "backlog",
        # G4：分类型行动分句（已带 count），aiSummary 据此拼分类型行动句。
        "actionClause": action_clause,
    }
    if action is not None:
        todo["action"] = action
    return todo


def _backlog_todos(tenant_id: str) -> list[dict[str, Any]]:
    """从真实库现算业务运营员待办；每条 = 一类有积压（count>0）的待办，深链到既有办理页。

    M5：发布/平台审/异议受理三类（catalog-publish / resource-publish / catalog-platform-review /
    objection）re-grain 成 decision-list 行内载荷——**枚举**真实积压实体（不止计数）逐条挂决策。
    申请受理（多角色受理面）/ 督办（多步）/ 需求汇总（多步）保留 count + href 兜底（不 re-grain）。
    """
    catalog_repo = CatalogRepository()
    resource_repo = ResourceApiRepository()
    application_repo = ApplicationRepository()
    objection_repo = ObjectionRepository()
    supply_repo = SupplyDemandRepository()

    # M5 枚举（非计数）：发布/平台审/异议受理三类 list-then-build 行内项，count = len(实体表)。
    publish_entries = catalog_repo.list_entries(
        tenant_id=tenant_id, lifecycle_status="approved_pending_publish"
    )
    # D57⑧ 两级各自入账：平台审待办（正向部门审通过 + 反向部门审通过共用此态）归业务运营员，
    # 深链目录审核收件箱（BUSIAUDIT 档即平台审），零积压不投。
    platform_review_entries = catalog_repo.list_entries(
        tenant_id=tenant_id, lifecycle_status=_PLATFORM_REVIEW_STATUS
    )
    publish_assets = resource_repo.list_assets(
        tenant_id=tenant_id, lifecycle_status="approved_pending_publish"
    )
    objection_cases = project_pending_objection_cases(tenant_id=tenant_id)
    national_escalate = _national_escalate_records(application_repo, tenant_id)

    pending_applications = _count_pending_applications(application_repo, tenant_id)
    # 待督办异议 = 有 escalate 督办事件且未终结的 case（事件式升级闭环，j1-objection-authz.feature:46）。
    # 督办标记由 objection_process 现算（不改 case.status），零积压不投（无空死链）。
    pending_supervised = len(objection_repo.list_supervised_cases(tenant_id=tenant_id))
    pending_demands = sum(
        1
        for item in supply_repo.list_demands(tenant_id=tenant_id)
        if item.get("demand_phase") in _DEMAND_PROVIDER_PHASES
    )

    todos: list[dict[str, Any]] = [
        t
        for t in (
            # 待平台审核目录（M5 行内：通过/驳回）
            _emit_backlog_todo(
                item_id="backlog-catalog-platform-review",
                label="待平台审核目录",
                count=len(platform_review_entries),
                status="待审核",
                href="#/provider/inbox/catalog-review",
                action_clause=f"{len(platform_review_entries)} 个目录待平台审核",
                action=_decision_list_action(
                    [_catalog_review_item(e) for e in platform_review_entries]
                ),
            ),
            # 待发布目录（M5 行内：发布）
            _emit_backlog_todo(
                item_id="backlog-catalog-publish",
                label="待发布目录",
                count=len(publish_entries),
                status="待发布",
                href="#/provider",
                action_clause=f"{len(publish_entries)} 个目录待发布",
                action=_decision_list_action(
                    [_catalog_publish_item(e) for e in publish_entries]
                ),
            ),
            # 待发布资源（M5 行内：发布）
            _emit_backlog_todo(
                item_id="backlog-resource-publish",
                label="待发布资源",
                count=len(publish_assets),
                status="待发布",
                href="#/provider",
                action_clause=f"{len(publish_assets)} 个资源待发布",
                action=_decision_list_action(
                    [_resource_publish_item(a) for a in publish_assets]
                ),
            ),
            # 国家通道待转报（C9 归位）：国家级数据申请本级审核通过后，由业务运营员在工作台行内转报。
            _emit_backlog_todo(
                item_id="backlog-national-escalate",
                label="国家通道待转报",
                count=len(national_escalate),
                status="待转报",
                href="#/workbench",
                action_clause=f"{len(national_escalate)} 条国家级数据申请待转报",
                action=_decision_list_action(
                    [_national_escalate_item(r) for r in national_escalate]
                ),
            ),
            # 待受理申请（不 re-grain：受理面跨多角色 + 申请单一事实源在 sync 投影；保 count+href 兜底）。
            _emit_backlog_todo(
                item_id="backlog-application",
                label="待受理申请",
                count=pending_applications,
                status="待受理",
                href="#/request-flow",
                action_clause=f"{pending_applications} 条申请待受理",
            ),
            # 待受理异议（M5 行内：受理）
            _emit_backlog_todo(
                item_id="backlog-objection",
                label="待受理异议",
                count=len(objection_cases),
                status="待受理",
                href="#/provider/inbox/objection?scope=pending",
                action_clause=f"{len(objection_cases)} 条异议待受理",
                action=_decision_list_action(
                    [_objection_item(c) for c in objection_cases]
                ),
            ),
            # 待督办异议（不 re-grain：督办多步，保 count+href 兜底）。
            # 事件式升级闭环（j1-objection-authz.feature:46）：escalate 事件把 case 推进
            # 业务运营员督办队列，不改 status。深链既有异议收件箱（同收件箱按督办标记筛）。
            _emit_backlog_todo(
                item_id="backlog-objection-supervised",
                label="待督办异议",
                count=pending_supervised,
                status="待督办",
                href="#/provider/inbox/objection",
                action_clause=f"{pending_supervised} 条异议待督办抓办",
            ),
            # 待汇总需求（不 re-grain：汇总多步，保 count+href 兜底）。
            _emit_backlog_todo(
                item_id="backlog-demand",
                label="待汇总需求",
                count=pending_demands,
                status="待汇总",
                href="#/provider/inbox/demand-match",
                action_clause=f"{pending_demands} 项需求待汇总",
            ),
        )
        if t is not None
    ]
    return todos


def _list_assets_pending_review(
    tenant_id: str, *, api_side: bool, visible_org_codes: set[str] | None = None
) -> list[ResourceAssetRecord]:
    """待审核资产列表（lifecycle_status==pending_review），按 canonical kind 分流两条审核口径。

    api_side=True 取服务注册审核（canonical kind==api）；False 取挂接审核（其余，含 kind
    缺失脏行——藏行会让资产静默卡死在 pending_review）。两侧互斥不串。

    M8 部门隔离：部门管理员只取 owner_org 落在本机构可见域内的资产（list-then-filter，量小
    可全扫）。visible_org_codes 三态同 ReferenceService.org_in_scope：None=全局取全量、空集=
    fail-closed 取空、非空集=只取在域内行。M5 行内枚举与计数同源——返回**实体列表**供
    decision-list 逐条构造，count=len(列表)，过滤口径单一不漂移。
    """
    resource_repo = ResourceApiRepository()
    ref = ReferenceService()
    return [
        record
        for record in resource_repo.list_assets(
            tenant_id=tenant_id, lifecycle_status=_DEPT_REVIEW_STATUS
        )
        if (canonical_resource_kind(getattr(record, "resource_kind", None)) == _API_CANONICAL_KIND) is api_side
        and ref.org_in_scope(getattr(record, "owner_org_id", None), visible_org_codes, tenant_id=tenant_id)
    ]


def _manager_review_todos(
    tenant_id: str, *, visible_org_codes: set[str] | None = None
) -> list[dict[str, Any]]:
    """G4（D55 查缺补漏）：部门管理员供数侧审核 stage 待办（真实库现算，零积压不投，深链既有页）。

    照旧平台 v5「资源挂接审核 / 资源审核 = 部门管理员」校正后，部门管理员供数审核待办含四条
    （均深链 MANAGER 可达页，零积压不投，无空死链）：
      - 待审核目录 = catalog_entry.lifecycle_status==pending_review → /provider/inbox/catalog-review
      - 待审核反向编目草稿 = catalog_entry(source=reverse).draft → /provider/inbox/field-decision
        （D57⑧ 两级管线第一级部门审；口径与 confirm/reject 可办前置严格一致）
      - 待审核挂接资源 = resource_asset(kind∈{table,file}).pending_review → /provider/inbox/hookup-review
      - 待审核服务 = resource_asset(kind∈{api,service}).pending_review → /provider/wizard/api-service（行内审核）
    需求校核 / 目录撤销·变更·迁移审核本期无 MANAGER 可办理的 UI 收件箱 → 不投。

    M8 部门隔离：四类审核计数只数 owner_org 落在本机构可见域内的行（list-then-filter-count，
    量小可全扫）。visible_org_codes 三态：None=全局计全量（上帝视角/未限定）、空集=fail-closed
    计 0、非空集=只计在域内行（owner∈本机构 + 下级）。bare count_entries 已改为 list-then-filter。
    """
    catalog_repo = CatalogRepository()
    ref = ReferenceService()
    # M5 行内枚举：三类审核待办 list-then-filter 取在域实体（与计数同源、口径不漂移），
    # decision-list 逐条挂决策；M8 行级过滤在枚举处套牢，不把越界实体漏进行内列表。
    # 待审核目录：原 bare count_entries 无法行级过滤 owner_org → 改 list-then-filter（量小）。
    catalog_review_entries = [
        record
        for record in catalog_repo.list_entries(
            tenant_id=tenant_id, lifecycle_status=_DEPT_REVIEW_STATUS
        )
        if ref.org_in_scope(record.owner_org_id, visible_org_codes, tenant_id=tenant_id)
    ]
    # 与 provider_snapshot_projection 反向编目审核收件箱同口径（source=reverse ∧ draft）。
    reverse_review_entries = [
        record
        for record in catalog_repo.list_entries(tenant_id=tenant_id, lifecycle_status="draft")
        if isinstance(record.summary_json, dict)
        and record.summary_json.get("source") == "reverse"
        and ref.org_in_scope(record.owner_org_id, visible_org_codes, tenant_id=tenant_id)
    ]
    hookup_review_assets = _list_assets_pending_review(
        tenant_id, api_side=False, visible_org_codes=visible_org_codes
    )
    pending_api_review = len(
        _list_assets_pending_review(
            tenant_id, api_side=True, visible_org_codes=visible_org_codes
        )
    )
    todos: list[dict[str, Any]] = [
        t
        for t in (
            # 待审核目录（M5 行内：通过/驳回，同平台审 catalog.entry.review）
            _emit_backlog_todo(
                item_id="backlog-catalog-dept-review",
                label="待审核目录",
                count=len(catalog_review_entries),
                status="待审核",
                href="#/provider/inbox/catalog-review",
                action_clause=f"{len(catalog_review_entries)} 个目录待部门审核",
                action=_decision_list_action(
                    [_catalog_review_item(e) for e in catalog_review_entries]
                ),
            ),
            # 待审核反向编目草稿（M5 行内：通过/驳回，reverse_draft.confirm/reject）
            _emit_backlog_todo(
                item_id="backlog-reverse-draft-review",
                label="待审核反向编目草稿",
                count=len(reverse_review_entries),
                status="待审核",
                href="#/provider/inbox/field-decision",
                action_clause=f"{len(reverse_review_entries)} 个反向编目草稿待部门审核",
                action=_decision_list_action(
                    [_reverse_draft_review_item(e) for e in reverse_review_entries]
                ),
            ),
            # 待审核挂接资源（M5 行内：通过/驳回 return_for_fix，resource.asset.review）
            _emit_backlog_todo(
                item_id="backlog-hookup-review",
                label="待审核挂接资源",
                count=len(hookup_review_assets),
                status="待审核",
                href="#/provider/inbox/hookup-review",
                action_clause=f"{len(hookup_review_assets)} 个挂接资源待审核",
                action=_decision_list_action(
                    [_hookup_review_item(a) for a in hookup_review_assets]
                ),
            ),
            # 待审核服务（不 re-grain：服务审核走向导多步，保 count+href 兜底）。
            _emit_backlog_todo(
                item_id="backlog-api-review",
                label="待审核服务",
                count=pending_api_review,
                status="待审核",
                href="#/provider/wizard/api-service",
                action_clause=f"{pending_api_review} 个服务待审核",
            ),
        )
        if t is not None
    ]
    return todos


def _enrich_busiaudit_backlog(view: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    """业务运营员（ROLE_BUSIAUDIT）：在 ``sync_request_todos`` 已投的「逐单受理待办」上
    **叠加**真实库聚合积压（发布/异议/督办/需求/平台审），而非整体替换.

    历史上本分支整体 ``out["todos"] = _backlog_todos(tid)``，会丢弃 sync 逐单投的
    ``category="accept"`` 受理待办——那些待办现已携带行内决策载荷（``action``），是
    「申请受理」可内联办理的唯一载体。改为增量：保留逐单受理待办（携 action），把聚合
    积压**前插**（去重 by id），并**剔除聚合里的「待受理申请」候选**（id
    ``backlog-application``）——逐单受理待办已逐条覆盖它，避免与聚合计数重复双算。
    其余聚合候选（发布/异议/督办/需求/平台审）原样保留为深链待办。

    subtitle/aiSummary 按**合并后**列表现算，计数诚实（不再回退陈旧 seed 叙事）。
    """
    out = copy.deepcopy(view)
    existing = out.get("todos") or []
    existing_ids = {t.get("id") for t in existing}
    # 聚合积压剔「待受理申请」（逐单受理待办已覆盖）+ 去重（id 已在逐单待办里的不前插）。
    aggregate = [
        t
        for t in _backlog_todos(tenant_id)
        if t["id"] != "backlog-application" and t["id"] not in existing_ids
    ]
    todos = aggregate + existing
    out["todos"] = todos
    # 分类型行动分句（G4）：聚合候选用其 action 模板分句；逐单受理待办合成一条受理分句。
    clauses = [str(t["actionClause"]) for t in aggregate if t.get("actionClause")]
    accept_count = sum(1 for t in existing if str(t.get("category", "")) == "accept")
    if accept_count:
        clauses.append(f"{accept_count} 条申请待受理")
    other_count = len(existing) - accept_count
    if other_count:
        clauses.append(f"{other_count} 条其他待办")
    _rewrite_advice(
        out,
        clauses=clauses,
        action_titles=[str(t.get("title", "")) for t in todos],
        empty_summary="当前没有待办积压。",
        basis="待办数据从真实库现算（目录/资源发布态 + 申请受理/异议/督办 + 需求汇总相位）",
    )
    return out


def _enrich_manager_backlog(
    view: dict[str, Any],
    tenant_id: str,
    *,
    visible_org_codes: set[str] | None = None,
    org_provider_visible_request_ids: set[str] | None = None,
    org_visible_request_ids: set[str] | None = None,
) -> dict[str, Any]:
    """部门管理员（D55/P10·G4）：在既投部门审核待办上叠加供数侧审核待办（目录/挂接/服务审核）。

    保留 ``sync_request_todos`` 已投的 dept_approved 部门审核待办（可点深链），把现算的供数侧
    审核待办**前插**（去重 by id）。零积压不投供数审核待办（无空死链）。
    subtitle/aiSummary 同步重写为诚实信号（D57②/R-8：此前管理员一直漏出 seed 虚构
    「涉企采集准入待判定」叙事）。

    M8 部门隔离：供数侧审核待办计数按 visible_org_codes 收口到本机构可见域（None=全局）。
    「第七面」收口：``sync_request_todos`` 已投的申请审核待办（category review）按提供方
    ``org_provider_visible_request_ids`` 收口；汇总待办（category summary）仍按申请方∨提供方
    参与口径 ``org_visible_request_ids`` 收口。None=全量放行（全局视角），传集即只留域内单。
    """
    out = copy.deepcopy(view)
    review_todos = _manager_review_todos(tenant_id, visible_org_codes=visible_org_codes)
    existing = out.get("todos") or []
    if org_provider_visible_request_ids is not None:
        existing = _drop_unscoped_request_todos(
            existing,
            categories=_MANAGER_REVIEW_REQUEST_CATEGORIES,
            scoped_ids=org_provider_visible_request_ids,
        )
    if org_visible_request_ids is not None:
        existing = _drop_unscoped_request_todos(
            existing,
            categories=_MANAGER_SUMMARY_REQUEST_CATEGORIES,
            scoped_ids=org_visible_request_ids,
        )
    existing_ids = {t.get("id") for t in existing}
    prepended = [t for t in review_todos if t["id"] not in existing_ids]
    todos = prepended + existing
    out["todos"] = todos
    review_clauses = [str(t["actionClause"]) for t in prepended if t.get("actionClause")]
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


# 部门操作员申请进度待办的本地化态文案（与 request_service.status_text("draft") 一致）：
# sync_request_todos 给每张运行时单投一条 apply-progress 待办，其 status 字段即本地化态文案；
# 草稿单的态文案恒为「草稿」（status_text 的 draft 兜底），据此把草稿与在办分开聚合。
# R-003（已知约束 / 后续）：此处以**展示文案**判草稿，受限于 sync todo 仅携带本地化 status、
# 丢了 raw status_code；若 status_text 的 draft 文案改写（i18n/视角），草稿会静默落入「在办」桶
# （非崩溃，仅误分类）。彻底修需 sync_request_todos 在 todo 上多带 raw status_code、下游按码判，
# 属 sync todo 形状变更，建议独立小改，本处不扩大改面。
_OPERATOR_DRAFT_STATUS_TEXT = "草稿"
# apply-progress 待办标题尾缀的**单一事实源**（R-002）：sync.py 投
# ``{resourceName}{APPLY_PROGRESS_TODO_TITLE_SUFFIX}``，本模块反向剥同一常量现算出 resourceName
# 当行内 label。标题模板与 P3 读侧共享、不在 sync 改名；只把尾缀字面量收敛为本常量，
# producer(sync.py)/consumer(本模块) 同源，杜绝两处硬编码漂移致 label 静默退化。
APPLY_PROGRESS_TODO_TITLE_SUFFIX = "资源申请进度跟踪"

# 操作员首屏聚合卡稳定 id（前端展开态/理由框按此定位；与 backlog-* 同命名风格但属操作员个人视图）。
_OP_CARD_DRAFT = "my-draft-applications"
_OP_CARD_ACTIVE = "my-active-applications"
_OP_CARD_SUPPLEMENT = "my-supplement-tasks"


def _operator_resource_name(todo: dict[str, Any]) -> str:
    """从 apply-progress 待办标题反推 resourceName（行内 label）。

    sync_request_todos 的标题模板 = ``{resourceName}资源申请进度跟踪``（与 P3 读侧共享、
    不在 sync 改名）；剥掉固定尾缀即真实资源名。标题不含尾缀（异常/历史形状）时回落整标题，
    再不济回落申请单号（id），绝不留空 label。"""
    title = str(todo.get("title", "")).strip()
    if title.endswith(APPLY_PROGRESS_TODO_TITLE_SUFFIX):
        name = title[: -len(APPLY_PROGRESS_TODO_TITLE_SUFFIX)].strip()
        if name:
            return name
    return title or str(todo.get("id", ""))


def _operator_draft_item(todo: dict[str, Any]) -> dict[str, Any]:
    """草稿单行内项：提交申请（request.submit，basePayload.request_id）。

    context 取真实可得字段——资源名 + 当前态文案（草稿）；申请单创建时间不在 sync 投影的待办
    载荷里（标题/态/深链三字段，无时间字段），故不造时间行（诚实留白，不捏 created_at）。"""
    request_id = str(todo.get("id", ""))
    resource_name = _operator_resource_name(todo)
    return {
        "id": request_id,
        "label": resource_name,
        "context": _context(
            _ctx_row("资源", resource_name),
            _ctx_row("状态", todo.get("status")),
        ),
        "capability": "request.submit",
        "gate": "request.submit",
        "basePayload": {"request_id": request_id},
        "decisions": [
            {"label": "提交申请", "tone": "primary", "success": "已提交", "payload": {}}
        ],
    }


def _operator_aggregate_todos(todos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把部门操作员申请进度待办（逐单一行）聚合成 ≤3 张诚实摘要卡（纯函数，单测友好）。

    输入 = ``sync_request_todos`` 投影、已套 dept-scope 收口的逐单待办列表（每张运行时单一条
    apply-progress + 若干 supplement-* 待办）。首屏不再铺 N 行草稿墙，按职责聚合成计数头条卡：
      - 「草稿待提交」= status 文案为草稿的 apply-progress → 计数头条 + decision-list（逐条草稿挂
        「提交申请」，request.submit，basePayload.request_id）；href 兜底 #/request-flow。
      - 「申请在办」= 非草稿 apply-progress（已提交/审批中/受理中/补录中…）→ 计数头条 + href 兜底。
      - 「补录任务待完成」= supplement-* 类（镇街/现场补录）→ 计数头条 + href 兜底。
    每张卡复用 ``_emit_backlog_todo``/``_decision_list_action`` 模式（与 MANAGER 审核卡同源），
    零积压不投该卡（无空死链）。卡序：草稿 → 在办 → 补录。"""
    drafts: list[dict[str, Any]] = []
    active = 0
    supplements = 0
    for todo in todos:
        category = str(todo.get("category", ""))
        if category == "apply-progress":
            if str(todo.get("status", "")) == _OPERATOR_DRAFT_STATUS_TEXT:
                drafts.append(todo)
            else:
                active += 1
        elif category.startswith("supplement"):
            supplements += 1
    cards: list[dict[str, Any]] = [
        card
        for card in (
            _emit_backlog_todo(
                item_id=_OP_CARD_DRAFT,
                label="草稿待提交",
                count=len(drafts),
                status="待提交",
                href="#/request-flow",
                action_clause=f"{len(drafts)} 张草稿可继续提交",
                action=_decision_list_action([_operator_draft_item(t) for t in drafts]),
            ),
            _emit_backlog_todo(
                item_id=_OP_CARD_ACTIVE,
                label="申请在办",
                count=active,
                status="在办",
                href="#/request-flow",
                action_clause=f"{active} 条申请在办",
            ),
            _emit_backlog_todo(
                item_id=_OP_CARD_SUPPLEMENT,
                label="补录任务待完成",
                count=supplements,
                status="待完成",
                href="#/request-flow",
                action_clause=f"{supplements} 项补录任务待完成",
            ),
        )
        if card is not None
    ]
    return cards


def _enrich_operator_backlog(
    view: dict[str, Any], *, org_visible_request_ids: set[str] | None = None
) -> dict[str, Any]:
    """部门操作员（D57②/R-8）：申请进度首屏聚合成 ≤3 张诚实摘要卡（不再铺逐单草稿墙）。

    todos 由 ``sync_request_todos`` 真投影（每张运行时单一行 apply-progress + 补录）；本层先套
    dept-scope 收口，再 :func:`_operator_aggregate_todos` 聚合成「草稿待提交 / 申请在办 / 补录任务
    待完成」三卡（草稿卡带逐条 request.submit 行内决策，其余两卡 count + href 兜底）。subtitle /
    办理建议从 seed 虚构叙事改为真实进度现算（草稿≠在办，给可提交/在办/待完成指引、非计数复读），
    零进度给诚实空态。

    「第七面」收口：``sync_request_todos`` 把申请进度/补录待办（category apply-progress/
    supplement-*）投给了**全租户每张运行时单**——按 ``org_visible_request_ids``（本机构可见域，
    同 MANAGER + 快照 requests 面口径）收口到本机构申请。None=全量放行（全局视角）；空集=
    fail-closed 全丢；传集即只留域内单（裁决③「按个人」由 requests 面 mine 标记承载、非此处 drop）。
    """
    out = copy.deepcopy(view)
    todos = out.get("todos") or []
    if org_visible_request_ids is not None:
        todos = _drop_unscoped_request_todos(
            todos,
            categories=_OPERATER_REQUEST_CATEGORIES,
            scoped_ids=org_visible_request_ids,
        )
    # dept-scope 收口在**聚合之前**：先剔越界逐单待办，再按职责聚合成首屏摘要卡。
    cards = _operator_aggregate_todos(todos)
    out["todos"] = cards
    # 办理建议为诚实进度指引（草稿≠在办，非计数复读）：草稿给「可继续提交」、在办/补录各一句，
    # 用每卡的 actionClause 现算（如「3 张草稿可继续提交」「2 条申请在办」）。
    clauses = [str(c["actionClause"]) for c in cards if c.get("actionClause")]
    _rewrite_advice(
        out,
        clauses=clauses,
        action_titles=[str(c.get("title", "")) for c in cards],
        empty_summary="当前没有进行中的申请。",
        basis="申请进度从真实库现算（草稿/在办申请单状态 + 补录任务）",
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
    view: dict[str, Any],
    role: str,
    *,
    tenant_id: str | None = None,
    visible_org_codes: set[str] | None = None,
    caller_actor: str | None = None,
) -> dict[str, Any]:
    """工作台 todos / 办理建议从真实库现算，enrich 覆盖全部 5 角色（D57②/R-8）.

    与 ``discovery_snapshot_projection`` 同模式：**无条件以 DB 现算为准**——有积压给真实
    待办，零积压给诚实空列表（不回退陈旧 seed 文案）。subtitle/aiSummary 也据现算积压
    重写为诚实信号，消除 C-1 删演示单后遗留的虚构叙事（R-8）。

    - 业务运营员（ROLE_BUSIAUDIT）：在 ``sync_request_todos`` 已投的「逐单受理待办（携行内
      决策 action）」之上**叠加**真实库聚合积压（发布/异议/督办/需求/平台审，剔重复的「待受理
      申请」聚合，去重 by id），办理建议据合并列表现算。
    - 部门管理员（ROLE_ORGAN_MANAGER）：在 ``sync_request_todos`` 已投的「部门审核待办（dept_approved）」
      之上**叠加供数侧审核待办**（目录 / 挂接资源 / 服务注册待部门审 pending_review，D55/P10·G4），
      零积压不投；办理建议重写。**M8 部门隔离：仅此路径消费 visible_org_codes**——审核待办计数
      只数 owner_org 落在本机构可见域内的行（None=全局 / 空集=fail-closed 计 0 / 非空集=域内）。
      平台队列（BUSIAUDIT 待平台审核/发布/受理/汇总）刻意保持全局，不消费 visible_org_codes。
    - 部门操作员（ROLE_ORGAN_OPERATER）：维持「申请进度」形态（0609 docx，拒协作待办），
      办理建议从真实进度现算；申请进度/补录待办按本机构可见域收口（「第七面」，同 MANAGER）。
    - 安全审计员（ROLE_SECURITY_AUDIT）：纯只读监督岗，todos 恒空 + 只读监督指引。
    - 平台运维员（ROLE_SYSTEM）：运维核查语境，诚实空态/积压计数。
    """
    tid = tenant_id or get_runtime_tenant_id()
    # M8 部门隔离：仅部门管理员审核待办计数按 visible_org_codes 收口到本机构可见域；
    # 平台队列（BUSIAUDIT 待平台审核/待发布/待受理/待汇总）保持全局，不消费 visible_org_codes。
    # 「第七面」收口：部门管理员 review 用 provider-only，summary 用申请方∨提供方参与口径；
    # 操作员申请进度在 live actor 存在时按本人申请收口，使工作台计数与深链「我的申请」同口径。
    if role == _MANAGER_ROLE:
        return _enrich_manager_backlog(
            view, tid, visible_org_codes=visible_org_codes,
            org_provider_visible_request_ids=_org_provider_visible_request_ids(tid, visible_org_codes),
            org_visible_request_ids=_org_visible_request_ids(tid, visible_org_codes),
        )
    if role == "ROLE_ORGAN_OPERATER":
        return _enrich_operator_backlog(
            view,
            org_visible_request_ids=_actor_visible_request_ids(
                tid, visible_org_codes, caller_actor=caller_actor
            ),
        )
    if role == "ROLE_SECURITY_AUDIT":
        return _enrich_supervisor_view(view)
    if role == "ROLE_SYSTEM":
        return _enrich_ops_view(view)
    if role != _BUSIAUDIT_ROLE:
        return view
    return _enrich_busiaudit_backlog(view, tid)
