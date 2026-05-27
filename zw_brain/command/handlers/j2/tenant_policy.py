"""J2 tenant_policy handlers — 1 cap migrated from BrainService (F1 turn 4).

Method bodies physically migrated; `self.` → `brain.` substitution applied. Per-cap handler
functions registered in `zw_brain.command.dispatch.DISPATCH_TABLE`.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.command.serializers import governance as governance_ser
from zw_brain.domain import policy
from zw_brain.domain.policy import DomainAccessDeniedError
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEFAULT_TENANT_ID = get_runtime_tenant_id()


# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _evaluate_tenant_policy(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    tenant_id = str(payload.get("tenant_id", _DEFAULT_TENANT_ID))
    capability_id = str(payload.get("capability_id", payload.get("skill_id", payload.get("capability_slug", ""))))
    surface = str(payload.get("surface", "webui"))
    target_ref = payload.get("target_ref")
    role_code = str(payload.get("role_code", payload.get("role", ctx.role)))
    actor_snapshot = brain._safe_json(payload.get("actor_snapshot") or {})
    org_snapshot = brain._safe_json(payload.get("org_snapshot") or {})
    risk_context = brain._safe_json(payload.get("risk_context") or {})
    requested_role_codes = [str(item) for item in payload.get("role_codes") or []]

    role_codes = sorted({role_code, *requested_role_codes, *[str(item) for item in actor_snapshot.get("role_codes") or []]})
    policy_version = "tenant-policy:v1"
    audit_class = "read-trace"
    human_confirmation_required = False
    if not capability_id:
        return {
            "tenant_id": tenant_id,
            "capability_id": capability_id,
            "surface": surface,
            "role_code": role_code,
            "role_codes": role_codes,
            "target_ref": target_ref,
            "allowed": False,
            "source": "fail_closed",
            "decision_reason": "missing_capability_id",
            "human_confirmation_required": False,
            "audit_class": audit_class,
            "policy_version": policy_version,
            "policy_status": None,
            "policy": None,
            "legacy_candidates": [],
            "actor_snapshot": actor_snapshot,
            "org_snapshot": org_snapshot,
            "risk_context": risk_context,
        }

    # Action C — deps.repos.capability_package: DB or in-memory fallback; in-memory
    # returns None for unknown policy lookups, preserving prior None-check semantics.
    tenant_policy = deps.repos.capability_package.get_policy(capability_id, tenant_id=tenant_id)

    registry_roles: list[str] = []
    for candidate_role in role_codes:
        try:
            if f"{capability_id}.execute" in policy.permissions_for_role(candidate_role):
                registry_roles.append(candidate_role)
        except DomainAccessDeniedError:
            continue

    allowed = False
    source = "fail_closed"
    decision_reason = "missing_tenant_policy"
    policy_snapshot: dict[str, Any] | None = None

    candidates = [
        governance_ser.legacy_policy_candidate_to_dict(item)
        for item in deps.repos.governance_projection.list_policy_candidates(tenant_id=tenant_id)
        if item.capability_id == capability_id and (item.surface is None or item.surface == surface)
    ]

    if tenant_policy is not None:
        policy_snapshot = copy.deepcopy(tenant_policy.policy_json)
        policy_version = str(policy_snapshot.get("policyVersion") or policy_snapshot.get("version") or policy_version)
        audit_class = str(policy_snapshot.get("auditClass") or audit_class)
        human_confirmation_required = bool(policy_snapshot.get("requiresHuman", False))
        exposed_surfaces = {str(item) for item in (policy_snapshot.get("exposedSurfaces") or [])}
        tenant_policy_json = policy_snapshot.get("tenantPolicy") if isinstance(policy_snapshot.get("tenantPolicy"), dict) else {}
        allowed_policy_roles = {str(item) for item in (tenant_policy_json.get("role_codes") or tenant_policy_json.get("roles") or [])}
        effective_role_codes = set(role_codes) - {"ACCOUNT_ADMIN"}
        policy_role_matched = bool(allowed_policy_roles & effective_role_codes) if allowed_policy_roles else role_code in effective_role_codes
        registry_or_policy_roles = set(registry_roles) | ({role_code} if policy_role_matched else set())
        tenant_enabled = tenant_policy.policy_status == "enabled" and bool(policy_snapshot.get("enabled", False))
        if not tenant_enabled:
            allowed = False
            source = "tenant_capability_policy"
            decision_reason = "tenant_policy_disabled"
        elif exposed_surfaces and surface not in exposed_surfaces:
            allowed = False
            source = "tenant_capability_policy"
            decision_reason = "surface_not_exposed"
        elif not registry_or_policy_roles:
            allowed = False
            source = "brain_registry"
            decision_reason = "role_not_allowed_by_registry"
        else:
            allowed = True
            source = "tenant_capability_policy"
            decision_reason = "allowed_by_tenant_policy"
    else:
        allowed = False
        source = "fail_closed"
        decision_reason = "missing_tenant_policy"

    actor_role_codes = {str(item) for item in actor_snapshot.get("role_codes") or []}
    requested_role_set = {role_code, *requested_role_codes}
    actor_status = str(
        actor_snapshot.get("status")
        or actor_snapshot.get("binding_status")
        or actor_snapshot.get("iam_binding_status")
        or ""
    ).lower()
    blocked_actor_reasons = {
        "disabled": "actor_disabled",
        "inactive": "actor_disabled",
        "unmatched": "actor_unmatched",
        "iam_account_missing": "iam_account_missing",
    }
    actor_tenant_id = str(actor_snapshot.get("tenant_id") or "")
    org_tenant_id = str(org_snapshot.get("tenant_id") or "")
    actor_org_code = str(actor_snapshot.get("org_code") or "")
    org_code = str(org_snapshot.get("org_code") or "")

    if actor_status in blocked_actor_reasons:
        allowed = False
        source = "fail_closed"
        decision_reason = blocked_actor_reasons[actor_status]
    elif actor_tenant_id and actor_tenant_id != tenant_id:
        allowed = False
        source = "fail_closed"
        decision_reason = "cross_tenant_denied"
    elif org_tenant_id and org_tenant_id != tenant_id:
        allowed = False
        source = "fail_closed"
        decision_reason = "org_tenant_mismatch"
    elif actor_org_code and org_code and actor_org_code != org_code:
        allowed = False
        source = "fail_closed"
        decision_reason = "org_binding_mismatch"
    elif allowed and actor_role_codes and role_code not in actor_role_codes:
        allowed = False
        source = "fail_closed"
        decision_reason = "role_binding_mismatch"
    elif allowed and actor_role_codes and not requested_role_set.issubset(actor_role_codes):
        non_registry_roles = requested_role_set - {role_code}
        if non_registry_roles and not non_registry_roles.issubset(actor_role_codes):
            allowed = False
            source = "fail_closed"
            decision_reason = "role_binding_mismatch"
    elif risk_context.get("cross_tenant") and tenant_id != str(actor_snapshot.get("tenant_id") or tenant_id):
        allowed = False
        source = "fail_closed"
        decision_reason = "cross_tenant_denied"
    elif risk_context.get("high_risk") or risk_context.get("requires_human") or risk_context.get("human_confirmation_required"):
        human_confirmation_required = True

    return {
        "tenant_id": tenant_id,
        "capability_id": capability_id,
        "surface": surface,
        "role_code": role_code,
        "role_codes": role_codes,
        "target_ref": target_ref,
        "allowed": allowed,
        "source": source,
        "decision_reason": decision_reason,
        "human_confirmation_required": human_confirmation_required,
        "audit_class": audit_class,
        "policy_version": policy_version,
        "policy_status": tenant_policy.policy_status if tenant_policy is not None else None,
        "policy": policy_snapshot,
        "legacy_candidates": candidates,
        "actor_snapshot": actor_snapshot,
        "org_snapshot": org_snapshot,
        "risk_context": risk_context,
    }


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_tenant_policy_evaluate(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _evaluate_tenant_policy(brain, deps, ctx, payload)

