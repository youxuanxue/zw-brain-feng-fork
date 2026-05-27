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
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEFAULT_TENANT_ID = get_runtime_tenant_id()
_logger = logging.getLogger(__name__)


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


def _maybe_start_baseline_workflow(
    *,
    application_code: str,
    tenant_id: str,
    shared_type: Any,
    submitted_by: str,
) -> str | None:
    """从 baseline 启动审批工作流；任何异常以 logger.warning 记录后返 None（D4：不破业务主路径，但保留可观测）。"""
    if shared_type is None:
        return None
    SessionLocal = create_session_factory()
    try:
        with SessionLocal() as session:
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
            "approval_flow.baseline.hook.failed",
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
    resource_id: str,
    role: str,
    confirmed: bool,
    query: str = "",
    skill_id: str = "request.create",
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    options = options or {}
    resource = brain._resolve_resource_for_application(resource_id)
    canonical_id = resource["id"]
    existing = next(
        (
            item
            for item in brain._snapshot["requests"]
            if item.get("resourceId") == canonical_id and item["status"] in {"pending", "supplementing", "summary-pending"}
        ),
        None,
    )
    if existing is not None:
        raise InvalidStateError(f"active request already exists for resource {canonical_id}: {existing['id']}")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        request_id = brain._new_request_id()
        task_id = brain._delivery_task_id_for_request(request_id)
        query_text = query.strip() or brain._ui_state.get("discoveryQuery") or DEFAULT_DISCOVERY_QUERY
        fields = brain._requested_application_fields(resource, options)
        gap_fields = brain._application_gap_fields(options)
        time_window = brain._application_time_window(options)
        scope = brain._application_scope(resource, options)
        delivery_expectation = str(options.get("delivery_expectation") or options.get("deliveryExpectation") or "审批通过后以库表/文件资源交付，并保留交付回执与审计回放。")
        purpose = str(options.get("purpose") or query_text or f"复用 {resource['name']}，只申请本次确需字段。")
        review_note = f"围绕 {resource['name']} 发起最小必要申请：{', '.join(item['title'] for item in fields) or '待确认字段'}；缺口：{', '.join(gap_fields) or '暂无'}。"
        request = {
            "id": request_id,
            "resourceId": canonical_id,
            "resourceName": resource["name"],
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
            "status": "pending",
            "submittedAt": clock.now_datetime(),
            "auditId": audit_id,
            "chainAnchor": "pending",
            "templateCoverage": resource.get("coverage", "—"),
            "prefilledFields": brain._prefilled_fields_for_resource(resource, fields),
            "diffFields": brain._diff_fields_for_gap(gap_fields),
            "sourceEvidence": brain._application_source_evidence(resource, fields),
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
        brain._snapshot["requests"].insert(0, request)
        brain._snapshot["approvals"].insert(0, approval)
        brain._snapshot["delivery_tasks"].insert(0, delivery)
        brain._append_audit_feed(skill_id, request_id, "ok", actor)

        # E3 Wave-2 F2 hook：按 shared_type 自动启动审批流基线（不破业务主路径）
        approval_case_id = _maybe_start_baseline_workflow(
            application_code=request_id,
            tenant_id=_DEFAULT_TENANT_ID,
            shared_type=_extract_shared_type(options, resource),
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
    return brain._mutate(skill_id, role, confirmed, audit_payload, mutation)

def _submit_request(brain, request_id: str, role: str, confirmed: bool) -> dict[str, Any]:
    request = brain._request_by_id(request_id)
    if request["status"] != "need-fix":
        raise InvalidStateError("current request is not in resubmission state")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        request["status"] = "pending"
        request["submittedAt"] = clock.now_datetime()
        request["auditId"] = audit_id
        request["chainAnchor"] = "pending"
        request["timeline"].append(
            {
                "label": "已补齐后重新提交",
                "time": clock.now_datetime(),
                "note": "申请已重新进入受控准入，等待审批承接人员判定。",
            }
        )
        request["aiStatus"]["summary"] = "申请已按“模板复用 + 差异补录”方式重新提交，当前重新回到受控准入阶段。"
        request["aiStatus"]["nextAction"] = "建议审批承接人员重新核对差异字段责任边界。"
        delivery = brain._delivery_by_request_id(request_id)
        if delivery:
            delivery["status"] = "warning"
            delivery["updatedAt"] = clock.now_datetime()
            delivery["note"] = "申请已重新提交，等待准入判定后再决定是否进入基层补录链路。"
            delivery["history"].append(
                {
                    "time": clock.now_short_time(),
                    "state": "重新提交待判定",
                    "detail": "补齐后重新进入受控准入，未直接下发基层任务。",
                }
            )
            delivery["aiSummary"]["summary"] = "当前仍处于准入判定前，不应提前下发基层任务。"
            delivery["aiSummary"]["nextAction"] = "请先完成审批承接，再决定是否进入补录链路。"
        brain._append_audit_feed("request.resubmit", request_id, "ok", actor)
        return {"request_id": request_id, "status": request["status"]}

    return brain._mutate("request.submit", role, confirmed, {"request_id": request_id}, mutation)

def _get_request(brain, request_id: str) -> dict[str, Any]:
    store = brain._state_store.database_store
    request = brain._maybe_request(request_id)
    if request is None:
        if store is None:
            raise NotFoundError(request_id)
        record = next((item for item in store.application_repo.list_records(tenant_id=_DEFAULT_TENANT_ID) if item.application_code == request_id), None)
        if record is None:
            raise NotFoundError(request_id)
        return brain._application_record_to_request(record, store)
    request = copy.deepcopy(request)
    if store is None:
        return request
    for record in store.application_repo.list_records(tenant_id=_DEFAULT_TENANT_ID):
        if record.application_code == request_id:
            brain._overlay_application_record(request, record, store)
            break
    delivery = brain._delivery_by_request_id(request_id) or brain._delivery_task_from_record(request_id, store)
    request["taskId"] = delivery["id"] if delivery else None
    request["statusTimeline"] = brain._request_status_timeline(request, delivery)
    return request


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_application_resource_submit(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    if "purpose" in payload and not str(payload.get("purpose") or "").strip():
        raise InvalidStateError("application.resource.submit: purpose 必填，不能为空字符串")
    return _create_request(brain, str(payload["resource_id"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")), str(payload.get("query", brain._ui_state.get("discoveryQuery", ""))), "application.resource.submit", payload)

def handler_request_create(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _create_request(brain, str(payload["resource_id"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")), str(payload.get("query", brain._ui_state.get("discoveryQuery", ""))), options=payload)

def handler_request_submit(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _submit_request(brain, str(payload["request_id"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))

def handler_request_view(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _get_request(brain, str(payload["request_id"]))

def handler_request_list(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return {"items": brain.list_requests()}

