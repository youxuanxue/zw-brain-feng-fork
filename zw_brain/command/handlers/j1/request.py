"""J1 request handlers — 5 cap migrated from BrainService (F1 turn 6, J1 收官)。

E3 Wave-2 F2：application.resource.submit 提交后按 shared_type 自动启动审批流基线
（hook 失败不破业务主路径，D4 审计总线哲学）。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

import copy
from datetime import datetime, timedelta

import zw_brain.shared.clock as clock
from zw_brain.command.brain import DEFAULT_DISCOVERY_QUERY, InvalidStateError, NotFoundError
from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.domain.approval_flow_baseline import start_approval_workflow_from_baseline
from zw_brain.domain.approval_flow_schema import ApprovalFlowSchemaRepo
from zw_brain.domain.approval_flow_walker import (
    ApprovalFlowWalkError,
    start_approval_workflow_from_schema,
)
from zw_brain.domain.resource_kind import canonical_resource_kind
from zw_brain.domain.services import field_derivation, form_fill_service
from zw_brain.domain.services.reference_service import ReferenceService
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID

_logger = logging.getLogger(__name__)


def _reference() -> ReferenceService:
    return ReferenceService()


def _resolve_actor_org(actor: str, reference: ReferenceService) -> dict[str, Any] | None:
    """身份带出：actor → 其组织（org_code/org_name）。best-effort，未命中返 None（诚实，不捏造）。"""
    try:
        rec = reference.repo.get_actor_by_external_id(actor, tenant_id=_DEFAULT_TENANT_ID)
        if rec is None or not rec.org_code:
            return None
        organ = reference.organ(rec.org_code, tenant_id=_DEFAULT_TENANT_ID)
        return {"org_code": rec.org_code, "org_name": (organ or {}).get("org_name") or rec.org_code}
    except Exception:  # noqa: BLE001 — 身份带出旁路，失败不破创建主路径
        return None


def _extract_shared_type(options: dict[str, Any], resource: dict[str, Any]) -> Any:
    """从 payload/resource 多个常见位置抽 shared_type；不存在返 None。"""
    for key in ("shared_type", "share_type", "sharedType", "shareType"):
        value = options.get(key)
        if value is not None:
            return value
    repository = resource.get("repository") if isinstance(resource, dict) else None
    if isinstance(repository, dict):
        for key in ("shared_type", "share_type", "sharedType", "shareType"):
            value = repository.get(key)
            if value is not None:
                return value
    return None


def _resolved_shared_type(options: dict[str, Any], resource: dict[str, Any]) -> int | None:
    """共享方式整型解析：payload/resource 显式值优先，否则按资源 access_policy 回源
    （与申请卡投影 `_shared_type_for` 同源口径）。取不到返 None（按无条件兜底）。

    状态词汇桥接（j1-runtime-write-path-dual-track 方案 B，负责人 2026-06-11 裁）：
    有条件 (2) 直提/提交单须落 status='submitted' 进 D55/P21 受理两级队列——此前 UI 单
    一律落旧词汇 'pending'，受理两级状态机（只认 submitted）对其无可办动作，单据卡死。
    """
    raw = _extract_shared_type(options, resource)
    # canonical 资源行（resolve_resource_for_application 产物）把共享方式放 accessPolicy 块。
    if raw is None and isinstance(resource, dict):
        access = resource.get("accessPolicy")
        if isinstance(access, dict):
            for key in ("shared_type", "share_type", "sharedType", "shareType"):
                value = access.get(key)
                if value is not None:
                    raw = value
                    break
    # 末级回源 resource_asset.access_policy_json：canonical id 是旧资源码（与 asset 键不同名），
    # 先试 focusedResourceCode（=asset.resource_code）再试 id。
    if raw is None and isinstance(resource, dict):
        from zw_brain.domain.discovery_snapshot_projection import shared_type_for_resource  # noqa: PLC0415

        for rid in (resource.get("focusedResourceCode"), resource.get("id")):
            if rid:
                raw = shared_type_for_resource(str(rid), _DEFAULT_TENANT_ID)
                if raw is not None:
                    break
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _owner_org_code_from_resource(resource: dict[str, Any]) -> str:
    """资源提供方机构码（R11 方向 guard 的 owner 源）；取不到返 ''（guard fail-closed）。"""
    if not isinstance(resource, dict):
        return ""
    return str(
        (resource.get("repository") or {}).get("ownerOrgId")
        or resource.get("providerOrgId")
        or resource.get("ownerOrgId")
        or ""
    )


def _extract_project_code(options: dict[str, Any], resource: dict[str, Any]) -> str | None:
    """抽 project_code（项目级审批 schema 选择用）；不存在返 None → 通配/回落 baseline。"""
    for key in ("project_code", "projectCode", "project_id", "projectId"):
        value = options.get(key)
        if value:
            return str(value)
    repository = resource.get("repository") if isinstance(resource, dict) else None
    if isinstance(repository, dict):
        for key in ("project_code", "projectCode", "project_id", "projectId"):
            value = repository.get(key)
            if value:
                return str(value)
    return None


def _maybe_start_approval_workflow(
    *,
    application_code: str,
    tenant_id: str,
    shared_type: Any,
    project_code: str | None,
    submitted_by: str,
) -> str | None:
    """启动审批工作流：优先用项目级自定义 live schema 驱动（R14 兑现），无命中或走查失败
    则原样回落 baseline。任何异常以 logger.warning 记录后返 None（D4：不破业务主路径，
    但保留可观测）。baseline 路径行为零变化。"""
    if shared_type is None:
        return None
    SessionLocal = create_session_factory()
    try:
        with SessionLocal() as session:
            custom = ApprovalFlowSchemaRepo(session).find_live_for_scope(
                tenant_id, shared_type, project_code
            )
            if custom is not None:
                try:
                    case = start_approval_workflow_from_schema(
                        session,
                        application_code=application_code,
                        tenant_id=tenant_id,
                        schema=custom,
                        submitted_by=submitted_by,
                        context={"shared_type": shared_type, "project_code": project_code},
                    )
                    if case is not None:
                        return case.id
                except ApprovalFlowWalkError as walk_exc:
                    # 自定义 schema 结构问题（环/不可达/无步骤）→ fail-closed 回落 baseline。
                    # 走查在 DB 写入前发生，无半截 case；rollback 以防万一。
                    session.rollback()
                    _logger.warning(
                        "approval_flow.schema.walk.failed.fallback_baseline",
                        extra={
                            "application_code": application_code,
                            "schema_code": custom.schema_code,
                            "error_msg": str(walk_exc)[:500],
                        },
                    )
            case = start_approval_workflow_from_baseline(
                session,
                application_code=application_code,
                tenant_id=tenant_id,
                shared_type=shared_type,
                submitted_by=submitted_by,
            )
            return case.id if case is not None else None
    except Exception as exc:  # noqa: BLE001 — hook 不破业务，但失败必须可观测（R-001 fix）
        _logger.warning(
            "approval_flow.hook.failed",
            extra={
                "application_code": application_code,
                "tenant_id": tenant_id,
                "shared_type": shared_type,
                "submitted_by": submitted_by,
                "error_class": type(exc).__name__,
                "error_msg": str(exc)[:500],
            },
            exc_info=True,
        )
        return None


# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _create_request(
    brain,
    deps,
    ctx,
    resource_id: str,
    role: str,
    confirmed: bool,
    query: str = "",
    skill_id: str = "request.create",
    options: dict[str, Any] | None = None,
    *,
    as_draft: bool = False,
) -> dict[str, Any]:
    """创建资源申请。``as_draft=True``（G2，request.create 走查路径）→ 落 status='draft'，
    用户可在详情页查看 / 确认后手动 submit；草稿**不触发审批工作流**（草稿不该进审批）。
    ``as_draft=False``（application.resource.submit 直提路径，如供方受理起草）→ 落 'pending'
    并即时触发审批工作流（行为零变化）。"""
    options = options or {}
    resource = deps.services.catalog.resolve_resource_for_application(resource_id)
    # 申请单绑定资源码（0611 断点 C 修复）：按资源码申请时，解析出的 canonical 行是其父目录
    # 详情卡（id=目录码，如 j2-inline-*）+ focusedResourceCode=被申请的资源码。申请单
    # resourceId 必须落资源码——否则共享方式回源（_shared_type_for / shared_type_for_resource
    # 按 resourceId 查 resource_asset.access_policy_json）全失败，有条件单被误判无条件、
    # 受理即终，D55④ 受理→部门管理员审核两级被旁路。目录码直申（无 focused 资源）保持原语义。
    canonical_id = str(resource.get("focusedResourceCode") or resource["id"])
    # G2：已存在同资源「草稿」→ 直接重入该草稿（幂等，避免重复点「申请」刷出一堆草稿单），
    # 不报错；用户回到既有草稿继续编辑/确认提交。
    existing_draft = next(
        (
            item
            for item in deps.view.requests.list_all()  # Action C — read facade
            if item.get("resourceId") == canonical_id and item.get("status") == "draft"
        ),
        None,
    )
    if existing_draft is not None:
        task = deps.view.delivery.find_by_request_id(existing_draft["id"])
        return {
            "request_id": existing_draft["id"],
            "task_id": task["id"] if task else None,
            "status": existing_draft["status"],
            "reused_draft": True,
        }
    # 已提交在办的申请（待受理/审批中/补录/汇总中）仍拦——不允许对同资源重复发起在办申请。
    # 状态词汇桥接后有条件直提单落 'submitted'（受理两级入口态），一并计入在办。
    existing = next(
        (
            item
            for item in deps.view.requests.list_all()
            if item.get("resourceId") == canonical_id and item["status"] in {"pending", "submitted", "supplementing", "summary-pending"}
        ),
        None,
    )
    if existing is not None:
        raise InvalidStateError(f"active request already exists for resource {canonical_id}: {existing['id']}")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        request_id = deps.services.request.new_request_id()
        task_id = deps.services.delivery.task_id_for_request(request_id)
        query_text = query.strip() or DEFAULT_DISCOVERY_QUERY
        fields = deps.services.application.requested_fields(resource, options)
        gap_fields = deps.services.application.gap_fields(options)
        time_window = deps.services.application.time_window(options)
        scope = deps.services.application.scope(resource, options)
        delivery_expectation = str(options.get("delivery_expectation") or options.get("deliveryExpectation") or "审批通过后以库表/文件资源交付，并保留交付回执与审计回放。")
        purpose = str(options.get("purpose") or query_text or f"复用 {resource['name']}，只申请本次确需字段。")
        review_note = f"围绕 {resource['name']} 发起最小必要申请：{', '.join(item['title'] for item in fields) or '待确认字段'}；缺口：{', '.join(gap_fields) or '暂无'}。"
        # G2：草稿态 vs 直提态——request.create 走查路径落「草稿」，application.resource.submit 直提落「审批中」。
        # 状态词汇桥接（方案 B）：有条件共享 (shared_type=2) 直提单落 'submitted' 进受理两级队列
        # （D55/P21：业务运营员受理 → 部门管理员审核）；无条件保持 'pending'（单步受理即终路径）。
        shared_type_int = _resolved_shared_type(options, resource)
        if as_draft:
            initial_status = "draft"
        elif shared_type_int == 2:
            initial_status = "submitted"
        else:
            initial_status = "pending"
        # 提供方局名：owner_org_code → ReferenceService 组织投影取 org_name（单一事实源、不另造表）。
        # #280 holder「部门管理员·{局名}」靠它；取不到诚实留空、holder 退「部门管理员（部门审核）」。
        _provider_code = _owner_org_code_from_resource(resource)
        _provider_organ = _reference().organ(_provider_code) if _provider_code else None
        provider_org_name = str((_provider_organ or {}).get("org_name") or "").strip()
        request = {
            "id": request_id,
            "resourceId": canonical_id,
            "resourceName": resource["name"],
            # 共享方式随单存档（申请卡投影 _shared_type_for 显式值优先；access_policy 回源兜底）。
            "sharedType": shared_type_int,
            # 提供方机构码随单存档（R11 方向 guard 的 owner 源——guard 对空 owner fail-closed，
            # 不落此键则有条件二级部门审核对任何管理员都 403、单据永卡 dept_approved）。
            "owner_org_code": _provider_code,
            # 提供方局名随单存档（卡 providerOrgName←payload.provider_org_name；#280 holder 局名源）。
            "provider_org_name": provider_org_name,
            # R-006 fix: 部门名称由 applicantDept 字段单独表达；不再在 actor 文本里拼接（折叠后无法靠 role 判断身份）
            "applicant": actor,
            "applicantDept": "市营商环境专班",
            "purpose": purpose,
            "range": scope,
            "timeWindow": time_window,
            "requestedItems": fields,
            "gapFields": gap_fields,
            "deliveryExpectation": delivery_expectation,
            "applicationMaterials": {
                "purpose": purpose,
                "timeWindow": time_window,
                "scope": scope,
                "catalogCode": resource.get("repository", {}).get("catalogCode") or canonical_id,
                "resourceId": canonical_id,
                "requestedItems": fields,
                "gapFields": gap_fields,
                "deliveryExpectation": delivery_expectation,
                "minimal": True,
            },
            "expectedBy": (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d"),
            "status": initial_status,
            # 国家通道指示（C9）：申请方声明请求国家级数据时透传 channel_class=national，
            # 供 P3 国家通道 tab 据此筛「待转报」队列；缺省 internal（本省内共享）。
            "channelClass": str(options.get("channel_class") or "internal"),
            "submittedAt": clock.now_datetime(),
            "auditId": audit_id,
            "chainAnchor": "pending",
            "templateCoverage": resource.get("coverage", "—"),
            "prefilledFields": deps.services.application.prefilled_fields(resource, fields),
            "diffFields": deps.services.application.diff_fields_for_gap(gap_fields),
            "sourceEvidence": deps.services.application.source_evidence(resource, fields),
            "reviewFocus": [
                "申请字段是否保持最小必要",
                "缺口字段是否需要补充说明",
                "交付方式和使用时间窗是否清楚",
            ],
            "summaryResult": {
                "totalEntities": 0,
                "autoMerged": 0,
                "exceptions": 0,
                "note": "尚未进入基层任务；审批通过后才会生成预填任务与自动汇总链路。",
            },
            "returnFlow": [
                "通过后自动创建镇街 / 社区预填任务",
                "补录完成后自动生成汇总结果",
                "高频差异字段进入回流候选池",
            ],
            "timeline": [
                {
                    "label": "已发现可复用模板",
                    "time": clock.now_datetime(),
                    "note": f"系统识别当前需求优先命中 {resource['name']}。",
                },
                {
                    "label": "已生成共享申请",
                    "time": clock.now_datetime(),
                    "note": f"进入受控准入并生成 audit_id {audit_id}",
                },
                {
                    "label": "待审批承接人员判定",
                    "time": clock.now_datetime(),
                    "note": review_note,
                },
                {
                    "label": "待交付任务生成",
                    "time": clock.now_datetime(),
                    "note": f"交付期望：{delivery_expectation}",
                },
                {
                    "label": "待基层补录",
                    "time": "—",
                    "note": "审批通过后自动下发预填任务。",
                },
                {
                    "label": "待审核汇总",
                    "time": "—",
                    "note": "系统先自动汇总，再由 审核汇总人 只处理异常项。",
                },
            ],
            "aiDraft": {
                "recognized": [
                    f"已识别起点：{resource['name']}",
                    f"已识别申请字段：{', '.join(item['title'] for item in fields)}",
                ],
                "needConfirm": [
                    "申请字段是否已满足最小必要",
                    "时间窗、区域范围和交付期望是否需要补充",
                ],
                "missing": gap_fields,
                "risk": "若把整张表作为申请范围，后续会被退回为最小字段申请。",
                "attachments": [
                    "建议附“只申请必要字段”的说明",
                    "建议明确缺口字段由谁补齐及交付时间窗",
                ],
                "summary": f"本申请拟复用 {resource['name']}，只申请 {', '.join(item['title'] for item in fields)}，缺口字段单独说明。",
            },
            "aiStatus": {
                "summary": f"申请已从资源发现页进入受控准入，当前围绕 {resource['name']} 等待 审批人 判定最小字段范围。",
                "nextAction": "建议审批承接人员核对用途、时间窗、申请字段、缺口字段和交付期望。",
                "evidence": [
                    f"申请字段：{', '.join(item['title'] for item in fields)}",
                    f"缺口字段：{', '.join(gap_fields) or '暂无'}",
                    "已生成最小必要申请并进入受控准入",
                ],
            },
        }
        approval = {
            "id": request_id,
            "suggestion": "建议通过",
            "confidence": 0.92,
            "reason": [
                f"{resource['name']} 已有字段与 schema 证据",
                "当前申请只包含必要字段，未扩大为全量采集",
                f"交付期望已声明：{delivery_expectation}",
            ],
            "risk": [
                "需确认缺口字段由谁补齐并谁来确认",
                "需确认时间窗和区域范围是否足够明确",
            ],
            "counterfactual": "如果申请方绕开模板坚持新增整表，应转入补正或驳回。",
            "impact": "通过后将自动创建镇街 / 社区预填任务，并在补录完成后生成自动汇总结果。",
            "actions": ["通过", "退回补正", "驳回"],
            "draftNote": f"建议审批意见：同意围绕 {resource['name']} 按最小字段范围办理；缺口字段按申请说明补齐，不扩大为整表采集。",
            "exceptionItems": [
                *(f"缺口字段待确认：{field}" for field in gap_fields),
                "交付回执需保留审计链路",
            ],
            "autoSummary": "尚未进入自动汇总链；审批通过后会生成预填任务。",
        }
        delivery = {
            "id": task_id,
            "requestId": request_id,
            "resourceId": canonical_id,
            "resourceName": resource["name"],
            "name": f"{resource['name']} 交付任务",
            # T12（6.5#9）+ 0611 §B 方案 B：新建交付单按资源类型分流（API=查看授权、文件=下载、
            # 库表=「交换任务」单一入口）。discovery.resources 行已带规范化 kind（canonical_resource_kind
            # 投影），此处随交付单落字段，与 legacy 导入单（delivery_service._delivery_resource_kind）
            # 口径统一；缺类型→None（UI 回落「查看授权」单按钮）。
            "resourceKind": canonical_resource_kind(resource.get("kind")),
            "channel": "受控交付 + 审计回执",
            "status": "pending",
            "owner": "申请方 → 审批承接 → 交付执行",
            "updatedAt": clock.now_datetime(),
            "note": delivery_expectation,
            "history": [
                {
                    "time": clock.now_short_time(),
                    "state": "待受理",
                    "detail": "已生成最小必要申请，等待审批承接人员受理。",
                }
            ],
            "aiSummary": {
                "summary": "当前任务处于待受理阶段；平台已把申请字段、缺口字段和交付期望绑定到同一交付链路。",
                "nextAction": "请先由 审批人 审核最小必要字段范围。",
                "cause": "当前只是生成最小必要申请，还未形成正式交付授权。",
                "impact": "避免绕过受控准入直接扩大采集范围。",
            },
            "backflow": {
                "candidateObject": f"{resource['name']} 缺口字段候选",
                "candidateFields": gap_fields,
                "status": "待审批结论",
                "note": "待审批确认后，再按交付期望生成交付与审计回执。",
            },
            "summaryConfirmed": False,
        }
        # 表单填报（form-autofill）：装配可编辑字段 + 字段级 provenance。
        # 确定性带出（身份/机构→区划，derived 权威）+ AI 建议（ai_suggested 待确认，只填空）；
        # 用户在表单实填的字段=human（此后 autofill/AI 不覆盖）。AI 建议字段经
        # payload.ai_suggested_fields 显式传入（与用户实填分离，诚实区分来源），缺省 {}。
        ref = _reference()
        actor_org = _resolve_actor_org(actor, ref)
        ai_suggestions = options.get("ai_suggested_fields")
        ai_suggestions = ai_suggestions if isinstance(ai_suggestions, dict) else {}
        user_values = {k: options.get(k) for k in form_fill_service.FIELD_KEYS if options.get(k) not in (None, "")}
        ff_values, ff_prov = form_fill_service.build_initial(
            user_values, actor_org=actor_org, ai_suggestions=ai_suggestions, reference=ref, tenant_id=_DEFAULT_TENANT_ID
        )
        # 只持久化模型（值 + provenance）；formFields 是只读投影，由 _record_to_request_card
        # 读时现算（单一事实源，避免同值两处需手同步）。
        request["fieldValues"] = ff_values
        request["fieldProvenance"] = ff_prov

        # Action D — 直写单源：三张卡登记进 CardSession（必脏），写括号末尾
        # flush 落 application_record / approval_case / delivery_task。
        deps.brain_legacy._card_session.add_request(request)
        deps.brain_legacy._card_session.add_approval(approval)
        deps.brain_legacy._card_session.add_delivery(delivery)
        deps.append_audit_feed(skill_id, request_id, "ok", actor)

        # E3 Wave-2 F2 hook：优先项目级自定义 live schema 驱动，否则回落 baseline（不破业务主路径）。
        # G2：草稿不触发审批工作流——审批在用户手动 submit（draft→提交态）时才启动。
        # 工作流与 initial_status 共用同一解析值（access_policy 回源兜底）——此前裸 payload 抽取
        # 在 UI 不传 shared_type 时给 None，工作流被当无条件起，与受理两级口径漂移。
        approval_case_id = None
        if not as_draft:
            approval_case_id = _maybe_start_approval_workflow(
                application_code=request_id,
                tenant_id=_DEFAULT_TENANT_ID,
                shared_type=shared_type_int,
                project_code=_extract_project_code(options, resource),
                submitted_by=actor,
            )
        result: dict[str, Any] = {"request_id": request_id, "task_id": task_id, "status": request["status"]}
        if approval_case_id is not None:
            result["approval_case_id"] = approval_case_id
        return result

    audit_payload = {
        "resource_id": resource_id,
        "query": query,
        "purpose": options.get("purpose"),
        "time_window": options.get("time_window"),
        "requested_items": options.get("requested_items"),
        "gap_fields": options.get("gap_fields"),
        "delivery_expectation": options.get("delivery_expectation"),
    }
    return deps.write(ctx, audit_payload, mutation)

# 可手动提交（→ pending）的来源态：草稿（G2 首次提交）+ 待补正（退回后重新提交）。
_SUBMITTABLE_STATUSES = {"draft", "need-fix"}


def _submit_request(brain, deps, ctx, request_id: str, role: str, confirmed: bool) -> dict[str, Any]:
    request = deps.view.requests.find_by_id(request_id)
    from_status = request.get("status")
    if from_status not in _SUBMITTABLE_STATUSES:
        raise InvalidStateError("current request is not in a submittable state (draft / need-fix)")
    # G2：草稿首次提交 vs 退回补正后重提，文案区分（语义诚实）。
    is_draft_submit = from_status == "draft"

    # 状态词汇桥接（方案 B）：解析共享方式——随单存档值优先（创建时已落 sharedType），
    # 缺位则解析资源回源（best-effort，与下方审批 hook 共用；资源已下线时按无条件兜底，
    # 不让陈旧草稿因资源消失而无法提交——同 D4「不破业务主路径」契约）。
    resolved_resource: dict[str, Any] | None = None
    try:
        resolved_resource = deps.services.catalog.resolve_resource_for_application(
            request.get("resourceId") or request_id
        )
    except Exception as exc:  # noqa: BLE001 — 解析失败旁路，不破提交主路径
        _logger.warning(
            "request_submit.resource_resolve.failed",
            extra={"application_code": request_id, "error_msg": str(exc)[:500]},
        )
    shared_type_int = _resolved_shared_type(
        {"shared_type": request.get("sharedType")}, resolved_resource or {}
    )
    # 有条件 (2) → 'submitted' 进受理两级队列；无条件/未知 → 'pending'（单步受理即终路径）。
    target_status = "submitted" if shared_type_int == 2 else "pending"

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        request["status"] = target_status
        # 旧草稿补漏：创建早于 owner_org_code 存档的单，提交时从资源回填（R11 方向 guard 的
        # owner 源；guard 对空 owner fail-closed，缺位则二级部门审核永 403）。
        if not request.get("owner_org_code") and resolved_resource is not None:
            request["owner_org_code"] = _owner_org_code_from_resource(resolved_resource)
        # 同上：存量草稿补提供方局名（#280 holder 局名源；owner_org_code→organ→org_name）。
        if not request.get("provider_org_name") and resolved_resource is not None:
            _pc = _owner_org_code_from_resource(resolved_resource)
            _po = _reference().organ(_pc) if _pc else None
            request["provider_org_name"] = str((_po or {}).get("org_name") or "").strip()
        request["submittedAt"] = clock.now_datetime()
        request["auditId"] = audit_id
        request["chainAnchor"] = "pending"
        request["timeline"].append(
            {
                "label": "已提交申请" if is_draft_submit else "已补齐后重新提交",
                "time": clock.now_datetime(),
                "note": (
                    "草稿已确认提交，进入受控准入，等待审批承接人员判定。"
                    if is_draft_submit
                    else "申请已重新进入受控准入，等待审批承接人员判定。"
                ),
            }
        )
        request["aiStatus"]["summary"] = (
            "申请已确认提交并进入受控准入，等待 审批人 判定最小字段范围。"
            if is_draft_submit
            else "申请已按“模板复用 + 差异补录”方式重新提交，当前重新回到受控准入阶段。"
        )
        request["aiStatus"]["nextAction"] = (
            "建议审批承接人员核对用途、时间窗、申请字段与缺口字段。"
            if is_draft_submit
            else "建议审批承接人员重新核对差异字段责任边界。"
        )
        delivery = deps.view.delivery.find_by_request_id(request_id)
        if delivery:
            delivery["status"] = "pending" if is_draft_submit else "warning"
            delivery["updatedAt"] = clock.now_datetime()
            delivery["note"] = (
                "申请已提交，等待审批承接人员受理。"
                if is_draft_submit
                else "申请已重新提交，等待准入判定后再决定是否进入基层补录链路。"
            )
            delivery["history"].append(
                {
                    "time": clock.now_short_time(),
                    "state": "已提交待受理" if is_draft_submit else "重新提交待判定",
                    "detail": (
                        "草稿确认提交，进入受控准入，等待审批承接人员受理。"
                        if is_draft_submit
                        else "补齐后重新进入受控准入，未直接下发基层任务。"
                    ),
                }
            )
            delivery["aiSummary"]["summary"] = "当前处于准入判定前，不应提前下发基层任务。"
            delivery["aiSummary"]["nextAction"] = "请先完成审批承接，再决定是否进入补录链路。"
        # 提交担责审计（Q2：人手动提交=审批担责，不强制逐条确认，但留 AI 来源痕迹）。
        request["submitProvenanceAudit"] = form_fill_service.provenance_audit_snapshot(
            request.get("fieldProvenance") or {}
        )
        deps.append_audit_feed(
            "request.submit" if is_draft_submit else "request.resubmit", request_id, "ok", actor
        )
        # G2：草稿确认提交 → 此刻才启动审批工作流（承接 _create_request 草稿不触发的搬移）。
        # 资源解析已提前到状态判定处共用（best-effort 契约不变）：资源缺位仅跳过审批 hook。
        approval_case_id = None
        if is_draft_submit and resolved_resource is not None:
            approval_case_id = _maybe_start_approval_workflow(
                application_code=request_id,
                tenant_id=_DEFAULT_TENANT_ID,
                shared_type=shared_type_int,
                project_code=_extract_project_code({}, resolved_resource),
                submitted_by=actor,
            )
        out: dict[str, Any] = {"request_id": request_id, "status": request["status"]}
        if approval_case_id is not None:
            out["approval_case_id"] = approval_case_id
        return out

    return deps.write(ctx, {"request_id": request_id}, mutation)

def _update_field(brain, deps, ctx, request_id: str, field: str, value: Any, role: str) -> dict[str, Any]:
    """人原地修订草稿的一个字段 → 标 human+locked（此后 autofill/AI 不再覆盖），随后重跑派生。

    派生字段（kind=derived）只读、不可人改（派生权威，承方案口径）——拒绝并提示。
    """
    if not form_fill_service.is_known_field(field):
        raise InvalidStateError(f"request.field.update: 未知表单字段 {field}")
    spec = next((s for s in form_fill_service.FORM_FIELD_SPECS if s["key"] == field), None)
    if spec and spec["kind"] == "derived":
        raise InvalidStateError(f"request.field.update: 字段 {field} 为自动带出（派生）值，只读不可手填")

    request = deps.view.requests.find_by_id(request_id)
    if request is None:
        raise NotFoundError(request_id)
    if request.get("status") not in _SUBMITTABLE_STATUSES:
        raise InvalidStateError("request.field.update: 仅草稿/待补正态可原地修订")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        values = dict(request.get("fieldValues") or {})
        provenance = dict(request.get("fieldProvenance") or {})
        ref = _reference()
        values, provenance = field_derivation.apply_human_edit(
            values, provenance, field, value, actor=actor, reference=ref, tenant_id=_DEFAULT_TENANT_ID
        )
        # 持久化只存模型；formFields 现算用于本次响应（与 _record_to_request_card 同源）。
        request["fieldValues"] = values
        request["fieldProvenance"] = provenance
        deps.append_audit_feed("request.field.update", request_id, "ok", actor)
        return {"request_id": request_id, "field": field, "formFields": form_fill_service.assemble_form_fields(values, provenance)}

    return deps.write(ctx, {"request_id": request_id, "field": field}, mutation)


def _ai_suggest_draft(brain, deps, ctx, request_id: str, role: str) -> dict[str, Any]:
    """对草稿空字段生成 AI 建议（标 ai_suggested·待确认）。永不自动提交——人核对/修订后手动提交=担责。

    复用 application.draft.suggest 助手产出建议，经 orchestrate_fill 只填**空且非 human/derived**的
    可建议字段；人已填/派生字段一律不动（承方案口径）。
    """
    from zw_brain.command.handlers.j1 import application_assistants

    request = deps.view.requests.find_by_id(request_id)
    if request is None:
        raise NotFoundError(request_id)
    if request.get("status") not in _SUBMITTABLE_STATUSES:
        raise InvalidStateError("request.draft.ai_suggest: 仅草稿/待补正态可生成 AI 建议")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        suggest = application_assistants._do_draft_suggest(
            brain,
            deps,
            ctx,
            {
                "resource_name": request.get("resourceName") or "",
                "applicant_org": request.get("applicantDept") or request.get("applicant") or "",
                "use_case": request.get("purpose") or "",
                "request_id": request_id,
            },
        )
        suggested = suggest.get("suggested_fields") or {}
        values = dict(request.get("fieldValues") or {})
        provenance = dict(request.get("fieldProvenance") or {})
        values, provenance = field_derivation.orchestrate_fill(
            values, provenance, reference=_reference(), tenant_id=_DEFAULT_TENANT_ID, ai_suggestions=suggested
        )
        request["fieldValues"] = values
        request["fieldProvenance"] = provenance
        deps.append_audit_feed("request.draft.ai_suggest", request_id, "ok", actor)
        return {
            "request_id": request_id,
            "formFields": form_fill_service.assemble_form_fields(values, provenance),
        }

    return deps.write(ctx, {"request_id": request_id, "kind": "ai_suggest"}, mutation)


def _reference_options(deps, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    """前端选择器取参照 options：机构(搜索)/区划(下钻)/字典(枚举)。只读，不写库。"""
    ref = _reference()
    tenant_id = _DEFAULT_TENANT_ID
    if kind == "region":
        parent = str(payload.get("parent_code") or payload.get("parent_region_code") or "")
        items = ref.region_children(parent, tenant_id=tenant_id) if parent else []
        return {"kind": "region", "parent_code": parent, "options": items}
    if kind == "dict":
        dict_type = str(payload.get("dict_type") or "")
        if not dict_type:
            raise InvalidStateError("reference.dict.options: dict_type 必填")
        return {"kind": "dict", "dict_type": dict_type, "options": ref.dict_options(dict_type, tenant_id=tenant_id)}
    if kind == "organ":
        # 选择器机构搜索分页：keyword 模糊 + 可选 reference_region_code 过滤 + offset/limit，DB 层切片。
        # 注：刻意不收 org_code 做点查——选机构后的区划带出由 request.field.update 服务端
        # 经 reference.organ() 完成；且 org_code 会与框架注入的 actor 上下文同名字段相撞。
        # 入参用 reference_region_code，避开注入的 current_org_code/region_code 等上下文键。
        region_code = str(payload.get("reference_region_code") or "")
        keyword = str(payload.get("keyword") or "")
        offset = max(0, int(payload.get("offset") or 0))
        limit = min(50, max(1, int(payload.get("limit") or 20)))  # 硬上限 50，挡恶意大 limit
        page = ref.search_organ(keyword=keyword, region_code=region_code, offset=offset, limit=limit, tenant_id=tenant_id)
        return {
            "kind": "organ",
            "region_code": region_code,
            "keyword": keyword,
            "options": page["options"],
            "total": page["total"],
            "offset": offset,
            "limit": limit,
        }
    raise InvalidStateError(f"reference options: 未知类型 {kind}")


def _get_request(brain, deps, ctx, request_id: str) -> dict[str, Any]:
    store = deps.state_store.database_store
    request = deps.services.request.maybe_by_id(request_id)
    if request is None:
        if store is None:
            raise NotFoundError(request_id)
        record = deps.repos.application.get_record(request_id, tenant_id=_DEFAULT_TENANT_ID)
        if record is None:
            raise NotFoundError(request_id)
        return deps.services.application.record_to_request(record, store)
    request = copy.deepcopy(request)
    if store is None:
        return request
    record = deps.repos.application.get_record(request_id, tenant_id=_DEFAULT_TENANT_ID)
    if record is not None:
        deps.services.application.overlay_record(request, record, store)
    delivery = deps.view.delivery.find_by_request_id(request_id) or deps.services.delivery.task_from_record(request_id, store)
    request["taskId"] = delivery["id"] if delivery else None
    request["statusTimeline"] = deps.services.request.status_timeline(request, delivery)
    return request


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_application_resource_submit(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    if "purpose" in payload and not str(payload.get("purpose") or "").strip():
        raise InvalidStateError("application.resource.submit: purpose 必填，不能为空字符串")
    return _create_request(brain, deps, ctx, str(payload["resource_id"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")), str(payload.get("query", DEFAULT_DISCOVERY_QUERY)), "application.resource.submit", payload)

def handler_request_create(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    # G2：request.create = P2「申请资源」走查入口 → 落草稿（可查看可编辑），用户确认后手动 submit。
    return _create_request(brain, deps, ctx, str(payload["resource_id"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")), str(payload.get("query", DEFAULT_DISCOVERY_QUERY)), options=payload, as_draft=True)

def handler_request_submit(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _submit_request(brain, deps, ctx, str(payload["request_id"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))

def handler_request_view(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _get_request(brain, deps, ctx, str(payload["request_id"]))

def handler_request_list(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return {"items": brain.list_requests()}


def handler_request_field_update(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None
    return _update_field(
        brain, deps, ctx,
        str(payload["request_id"]), str(payload["field"]), payload.get("value", ""),
        str(payload.get("role", ctx.role)),
    )


def handler_request_draft_ai_suggest(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None
    return _ai_suggest_draft(brain, deps, ctx, str(payload["request_id"]), str(payload.get("role", ctx.role)))


def handler_reference_organ_options(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    return _reference_options(deps, "organ", payload)


def handler_reference_region_options(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    return _reference_options(deps, "region", payload)


def handler_reference_dict_options(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    return _reference_options(deps, "dict", payload)

