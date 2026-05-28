"""J1 approval handlers — 4 cap migrated from BrainService (F1 turn 6, J1 收官)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass
import copy

from zw_brain.command.brain import _DEFAULT_TENANT_ID, BrainServiceError, NotFoundError
from zw_brain.command.deps import HandlerDeps, SkillContext

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _get_approval(brain, deps, ctx, request_id: str) -> dict[str, Any]:
    store = deps.state_store.database_store
    approval = copy.deepcopy(brain._approval_by_id(request_id)) if brain._maybe_approval(request_id) is not None else {"id": request_id}
    if store is None:
        if "requestId" not in approval:
            raise NotFoundError(request_id)
        return approval
    case = next((item for item in deps.repos.approval.list_cases(tenant_id=_DEFAULT_TENANT_ID) if item.application_code == request_id), None)
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
                "approverScope": brain._mask_actor_payload(copy.deepcopy(item.approver_scope_json)),
            }
            for item in step_records
        ]
        approval["decisions"] = [
            {
                "decision": item.decision,
                "decisionReason": item.decision_reason,
                "actorSnapshot": brain._mask_actor_payload(copy.deepcopy(item.actor_snapshot_json)),
                "evidence": copy.deepcopy(item.evidence_json),
            }
            for item in decision_records
        ]
        approval["legacyMappings"].extend(brain._legacy_mapping_refs(store, "approval_step", [str(item.id) for item in step_records]))
        approval["legacyMappings"].extend(brain._legacy_mapping_refs(store, "approval_decision", [str(item.id) for item in decision_records]))
    if delivery is not None:
        approval["grantEvidence"] = deps.services.delivery.grant_evidence(delivery)
    approval["recommendedDecision"] = brain._approval_recommendation(approval, request, delivery)
    for key, value in brain._approval_business_defaults(request, delivery).items():
        approval.setdefault(key, value)
    return approval

def _review_request(brain, deps, ctx, request_id: str, decision: str, role: str, confirmed: bool, skill_id: str = "approval.review_decide") -> dict[str, Any]:
    normalized = {"approve": "approve_reuse", "reject": "reject_duplicate"}.get(decision, decision)
    if normalized in {"approve_reuse", "approve_with_supplement", "return_for_fix", "reject_duplicate", "route_to_provider_or_catalog_admin"}:
        store = deps.state_store.database_store
        if store is not None and deps.services.application.request_from_record(request_id, store) is not None:
            return brain._review_application_record(request_id, normalized, role, confirmed, skill_id)
    if normalized in {"approve_reuse", "approve_with_supplement"}:
        return brain._approve_request(request_id, role, confirmed, skill_id, decision=normalized)
    if normalized == "return_for_fix":
        return brain._return_request_for_fix(request_id, role, confirmed, skill_id, decision=normalized)
    if normalized == "reject_duplicate":
        return brain._reject_request(request_id, role, confirmed, skill_id, decision=normalized)
    if normalized == "route_to_provider_or_catalog_admin":
        return brain._route_request_for_catalog_confirmation(request_id, role, confirmed, skill_id)
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

