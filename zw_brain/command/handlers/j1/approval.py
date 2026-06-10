"""J1 approval handlers — 4 cap migrated from BrainService (F1 turn 6, J1 收官)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass
import copy

from zw_brain.command.brain import _DEFAULT_TENANT_ID, BrainServiceError, NotFoundError
from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.domain.errors import AccessDeniedError
from zw_brain.domain.serializers.legacy_mapping import legacy_mapping_refs
from zw_brain.shared.sensitive_mask import mask_actor_payload

# j1-approval-conditional 第二级部门审核的可信角色门控（R-001 fix；D55/P21 后为第二级）：
# application.dept_approve.execute 的 PERMISSION_ROLES 含 OPERATER 仅为 resubmit（申请人补件
# 重提）复用同一 capability。非 resubmit 路径（approve/reject）= 部门审核（第二级终审），SPEC
# 角色边界是「仅提供方部门管理员」，必须按 ctx.role（BFF 可信身份）二次门控，不能让 OPERATER 用
# decision='approve' 经 dept_approve 审批路径越权。
ROLE_ORGAN_MANAGER = "ROLE_ORGAN_MANAGER"

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _get_approval(brain, deps, ctx, request_id: str) -> dict[str, Any]:
    store = deps.state_store.database_store
    approval = copy.deepcopy(deps.services.request.approval_by_id(request_id)) if deps.services.request.maybe_approval_by_id(request_id) is not None else {"id": request_id}
    if store is None:
        if "requestId" not in approval:
            raise NotFoundError(request_id)
        return approval
    case = deps.repos.approval.get_case(request_id, tenant_id=_DEFAULT_TENANT_ID)
    if case is None and "requestId" not in approval:
        raise NotFoundError(request_id)
    approval["requestId"] = request_id
    request = brain.get_request(request_id)
    delivery = deps.view.delivery.find_by_request_id(request_id) or deps.services.delivery.task_from_record(request_id, store)
    approval["statusTimeline"] = deps.services.request.status_timeline(request, delivery)
    approval["applicationMaterials"] = copy.deepcopy(request.get("applicationMaterials", {}))
    approval["reuseCandidate"] = copy.deepcopy(request.get("reuseCandidate", {}))
    approval["fieldEvidence"] = {
        "fieldBindingSummary": copy.deepcopy(request.get("fieldBindingSummary", {})),
        "fieldBindings": copy.deepcopy(request.get("fieldBindings", [])),
        "schemaSnapshots": copy.deepcopy(request.get("schemaSnapshots", [])),
        "sensitivePolicy": copy.deepcopy(request.get("sensitivePolicy", {})),
        "resourceAssets": copy.deepcopy(request.get("resourceAssets", [])),
    }
    approval["historicalContext"] = copy.deepcopy(request.get("historicalContext", {}))
    approval["qualityEvidence"] = copy.deepcopy(request.get("qualityEvidence", {}))
    approval["legacyMappings"] = copy.deepcopy(request.get("legacyMappings", []))
    approval["reviewBoundary"] = copy.deepcopy(request.get("reviewBoundary", {}))
    if case is not None:
        approval["case"] = {
            "currentStatus": case.current_status,
            "currentStep": case.current_step,
        }
        step_records = deps.repos.approval.list_steps(request_id)
        decision_records = deps.repos.approval.list_decisions(request_id)
        approval["steps"] = [
            {
                "stepNo": item.step_no,
                "stepName": item.step_name,
                "decisionMode": item.decision_mode,
                "status": item.status,
                "approverScope": mask_actor_payload(copy.deepcopy(item.approver_scope_json)),
            }
            for item in step_records
        ]
        approval["decisions"] = [
            {
                "decision": item.decision,
                "decisionReason": item.decision_reason,
                "actorSnapshot": mask_actor_payload(copy.deepcopy(item.actor_snapshot_json)),
                "evidence": copy.deepcopy(item.evidence_json),
            }
            for item in decision_records
        ]
        approval["legacyMappings"].extend(legacy_mapping_refs(store, "approval_step", [str(item.id) for item in step_records]))
        approval["legacyMappings"].extend(legacy_mapping_refs(store, "approval_decision", [str(item.id) for item in decision_records]))
    if delivery is not None:
        approval["grantEvidence"] = deps.services.delivery.grant_evidence(delivery)
    approval["recommendedDecision"] = deps.services.request.approval_recommendation(approval, request, delivery)
    for key, value in deps.services.request.approval_business_defaults(request, delivery).items():
        approval.setdefault(key, value)
    return approval

def _review_request(brain, deps, ctx, request_id: str, decision: str, role: str, confirmed: bool, skill_id: str = "approval.review_decide") -> dict[str, Any]:
    normalized = {"approve": "approve_reuse", "reject": "reject_duplicate"}.get(decision, decision)
    if normalized in {"approve_reuse", "approve_with_supplement", "return_for_fix", "reject_duplicate", "route_to_provider_or_catalog_admin"}:
        store = deps.state_store.database_store
        if store is not None and deps.services.application.request_from_record(request_id, store) is not None:
            return deps.services.request.review_application_record(request_id, normalized, role, confirmed, skill_id)
    if normalized in {"approve_reuse", "approve_with_supplement"}:
        return deps.services.request.approve(request_id, role, confirmed, skill_id, decision=normalized)
    if normalized == "return_for_fix":
        return deps.services.request.return_for_fix(request_id, role, confirmed, skill_id, decision=normalized)
    if normalized == "reject_duplicate":
        return deps.services.request.reject(request_id, role, confirmed, skill_id, decision=normalized)
    if normalized == "route_to_provider_or_catalog_admin":
        return deps.services.request.route_for_catalog_confirmation(request_id, role, confirmed, skill_id)
    raise BrainServiceError(f"unsupported review decision: {decision}")


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_approval_view(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _get_approval(brain, deps, ctx, str(payload["request_id"]))

def handler_application_resource_review(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _review_request(brain, deps, ctx, str(payload["request_id"]), str(payload["decision"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")), "application.resource.review")

def handler_approval_case_decide(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _review_request(brain, deps, ctx, str(payload["request_id"]), str(payload["decision"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")), "approval.case.decide")

def handler_approval_review_decide(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _review_request(brain, deps, ctx, str(payload["request_id"]), str(payload["decision"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))


def _actor_org_code(ctx: SkillContext, payload: dict[str, Any]) -> str:
    """Resolve the acting org_code from the trusted payload (BFF current_org_code).

    build_trusted_skill_payload stamps current_org_code → payload['org_code']; the
    actor_snapshot is also available for the multi-context case. R11 direction +
    self_approval guard both read this org.
    """
    snapshot = payload.get("actor_snapshot") if isinstance(payload.get("actor_snapshot"), dict) else {}
    return str(
        payload.get("org_code")
        or payload.get("current_org_code")
        or snapshot.get("current_org_code")
        or snapshot.get("org_code")
        or ""
    )


def handler_application_dept_approve(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    """J1 有条件共享第二级（D55/P21）：部门管理员审核终审（dept_approved → granted / rejected）。

    decision='resubmit' 走申请人补件重提（rejected → submitted, round+1）。
    （key application.dept_approve 不改名；语义由「第一步部门审」对调为「第二级部门审核终审」。）
    """
    svc = deps.services.conditional_approval
    request_id = str(payload["request_id"])
    decision = str(payload.get("decision", "approve"))
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    actor_org = _actor_org_code(ctx, payload)
    if decision == "resubmit":
        return svc.applicant_resubmit(request_id, role, confirmed, actor_org_code=actor_org, skill_id=ctx.skill_id)
    # R-001 fix: 部门审核（approve/reject）= 仅提供方部门管理员。application.dept_approve.execute
    # 的 PERMISSION_ROLES 含 OPERATER 仅为 resubmit 复用同 capability；非 resubmit 路径按 ctx.role
    # （BFF 可信身份，非 payload.role）门控为 ROLE_ORGAN_MANAGER，否则越权（OPERATER 用
    # decision='approve' 本可经 dept_approve 走审批路径，仅被 org 方向 / self-approval 拦）。
    if ctx.role != ROLE_ORGAN_MANAGER:
        raise AccessDeniedError(
            f"application.dept_approve decision={decision!r} (部门审核) requires role "
            f"{ROLE_ORGAN_MANAGER}; got {ctx.role!r}"
        )
    return svc.dept_approve(
        request_id,
        role,
        confirmed,
        actor_org_code=actor_org,
        decision=decision,
        note=str(payload.get("note") or payload.get("reason") or ""),
        skill_id=ctx.skill_id,
    )


def handler_application_platform_approve(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    """J1 有条件共享第一级（D55/P21）：业务运营员受理（submitted → dept_approved / rejected）。

    （key application.platform_approve 不改名；语义由「第二步平台复核」对调为「第一级受理」。
    受理是平台级动作，角色由 policy application.platform_approve.execute={ROLE_BUSIAUDIT} 门控，
    不做 self/方向校验。）
    """
    svc = deps.services.conditional_approval
    return svc.platform_decide(
        str(payload["request_id"]),
        str(payload.get("role", ctx.role)),
        bool(payload.get("confirmed")),
        actor_org_code=_actor_org_code(ctx, payload),
        decision=str(payload.get("decision", "approve")),
        note=str(payload.get("note") or payload.get("reason") or ""),
        skill_id=ctx.skill_id,
    )

