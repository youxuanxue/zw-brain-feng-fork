"""J2 governance handlers — 3 cap migrated from BrainService (F1 turn 4).

Method bodies physically migrated; `self.` → `brain.` substitution applied. Per-cap handler
functions registered in `zw_brain.command.dispatch.DISPATCH_TABLE`.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from zw_brain.command.brain import BrainServiceError, _count_by
from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.command.serializers import adapter as adapter_ser
from zw_brain.command.serializers import governance as governance_ser
from zw_brain.domain import policy
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id
from zw_brain.skill_registration.runtime import get_manifest

_DEFAULT_TENANT_ID = get_runtime_tenant_id()


# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _get_governance_iam_overview(brain, payload: dict[str, Any]) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    tenant_id = str(payload.get("tenant_id", _DEFAULT_TENANT_ID))
    status_filter = str(payload.get("binding_status", payload.get("status", "")) or "")
    capability_filter = str(payload.get("capability_id", payload.get("capability_slug", "")) or "")
    issue_filter = str(payload.get("issue_type", "") or "")
    repo = deps.repos.governance_projection
    store = brain._state_store.database_store
    tenants = [governance_ser.tenant_projection_to_dict(item) for item in repo.list_tenants() if not tenant_id or item.tenant_id == tenant_id]
    orgs = [governance_ser.org_projection_to_dict(item) for item in repo.list_orgs(tenant_id=tenant_id)]
    regions = [governance_ser.region_projection_to_dict(item) for item in repo.list_regions(tenant_id=tenant_id)]
    roles = [governance_ser.role_projection_to_dict(item) for item in repo.list_roles(tenant_id=tenant_id)]
    raw_actors = repo.list_actors(tenant_id=tenant_id)
    actors = [governance_ser.actor_projection_to_dict(item) | {"actor_snapshot": brain._actor_snapshot_from_projection(item, claims={})} for item in raw_actors]
    role_filter = str(payload.get("role_code", "") or "")
    actor_filter = str(payload.get("actor_id", payload.get("external_actor_id", "")) or "")
    if role_filter:
        roles = [item for item in roles if item.get("role_code") == role_filter]
    actors = [item for item in actors if brain._filter_governance_actor(item, status_filter=status_filter, role_filter=role_filter, actor_filter=actor_filter)]
    policies = [governance_ser.tenant_policy_to_dict(item) for item in store.capability_package_repo.list_policies(tenant_id=tenant_id)] if store is not None else []
    if capability_filter:
        policies = [item for item in policies if item.get("package_slug") == capability_filter]
    candidates = [governance_ser.legacy_policy_candidate_to_dict(item) for item in repo.list_policy_candidates(tenant_id=tenant_id)]
    if capability_filter:
        candidates = [item for item in candidates if item.get("capability_id") == capability_filter]
    adapter_runs = [adapter_ser.adapter_run_to_dict(item) for item in deps.repos.external_adapter.list_run_records(tenant_id=tenant_id, adapter_slug="legacy.bsp.governance")]
    issues = brain._governance_import_issues(adapter_runs)
    if issue_filter:
        issues = [item for item in issues if item.get("type") == issue_filter]
    audit_events = brain._governance_audit_events(tenant_id=tenant_id, capability_filter=capability_filter, actor_filter=actor_filter)
    sample_actor = actors[0] if actors else None
    sample_policy = policies[0] if policies else None
    sample_org = next((item for item in orgs if sample_actor and item.get("org_code") == sample_actor.get("org_code")), orgs[0] if orgs else None)
    policy_probe = None
    if sample_policy is not None:
        actor_snapshot = copy.deepcopy(sample_actor.get("actor_snapshot")) if sample_actor else {}
        if actor_snapshot and not actor_snapshot.get("role_codes"):
            actor_snapshot["role_codes"] = list(sample_actor.get("role_codes_json") or [])
        policy_probe = brain.evaluate_tenant_policy(
            {
                "tenant_id": tenant_id,
                "capability_id": sample_policy["package_slug"],
                "surface": str(payload.get("surface", "api")),
                "role": str(payload.get("role", (actor_snapshot.get("role_codes") or [brain._ui_state["role"]])[0])),
                "actor_snapshot": actor_snapshot,
                "org_snapshot": copy.deepcopy(sample_org or {}),
                "risk_context": brain._safe_json(payload.get("risk_context") or {}),
            }
        )
    return {
        "tenant_id": tenant_id,
        "filters": {"binding_status": status_filter or None, "role_code": role_filter or None, "actor_id": actor_filter or None, "capability_id": capability_filter or None, "issue_type": issue_filter or None},
        "summary": {
            "tenant_count": len(tenants),
            "org_count": len(orgs),
            "region_count": len(regions),
            "actor_count": len(actors),
            "role_count": len(roles),
            "policy_count": len(policies),
            "issue_count": len(issues),
            "audit_count": len(audit_events),
            "binding_status_counts": _count_by(actors, "status"),
        },
        "tenants": tenants,
        "orgs": orgs,
        "regions": regions,
        "actors": actors,
        "roles": roles,
        "tenant_policies": policies,
        "legacy_policy_candidates": candidates,
        "import_issues": issues,
        "adapter_runs": adapter_runs,
        "audit_events": audit_events,
        "policy_probe": policy_probe,
    }

def _list_policy_mapping_candidates(brain, payload: dict[str, Any]) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    tenant_id = str(payload.get("tenant_id", _DEFAULT_TENANT_ID))
    repo = deps.repos.governance_projection
    records = repo.list_policy_candidates(
        tenant_id=tenant_id,
        candidate_status=str(payload.get("candidate_status") or payload.get("status") or "") or None,
        legacy_system=str(payload.get("legacy_system") or "") or None,
        legacy_role_ref=str(payload.get("legacy_role_ref") or payload.get("role_code") or "") or None,
        capability_id=str(payload.get("capability_id") or payload.get("capability_slug") or "") or None,
        surface=str(payload.get("surface") or "") or None,
    )
    items = [governance_ser.legacy_policy_candidate_to_dict(item) for item in records]
    status_counts: dict[str, int] = {}
    for item in items:
        status = str(item.get("candidate_status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "tenant_id": tenant_id,
        "filters": {
            "candidate_status": payload.get("candidate_status") or payload.get("status") or None,
            "legacy_system": payload.get("legacy_system") or None,
            "legacy_role_ref": payload.get("legacy_role_ref") or payload.get("role_code") or None,
            "capability_id": payload.get("capability_id") or payload.get("capability_slug") or None,
            "surface": payload.get("surface") or None,
        },
        "summary": {"total": len(items), "status_counts": status_counts},
        "items": items,
        "export_report": {
            "generated_at": datetime.now(UTC).isoformat(),
            "tenant_id": tenant_id,
            "status_counts": status_counts,
            "total": len(items),
        },
    }

def _review_policy_mapping_candidates(brain, payload: dict[str, Any]) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    decision = str(payload.get("decision") or "").strip().lower()
    if decision not in {"approve", "reject", "approve_and_apply", "apply"}:
        raise BrainServiceError(f"unsupported review decision: {decision}")

    def _normalize_review_items(input_payload: dict[str, Any]) -> list[dict[str, str]]:
        rows = input_payload.get("items") if isinstance(input_payload.get("items"), list) else []
        if not rows and input_payload.get("legacy_permission_ref") and input_payload.get("capability_id"):
            rows = [input_payload]
        normalized: list[dict[str, str]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            legacy_permission_ref = str(row.get("legacy_permission_ref") or "")
            capability_id = str(row.get("capability_id") or "")
            if not legacy_permission_ref or not capability_id:
                continue
            normalized.append(
                {
                    "legacy_system": str(row.get("legacy_system") or input_payload.get("legacy_system") or "dsp-bsp"),
                    "legacy_permission_ref": legacy_permission_ref,
                    "capability_id": capability_id,
                }
            )
        return normalized

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        tenant_id = str(payload.get("tenant_id", _DEFAULT_TENANT_ID))
        review_note = str(payload.get("review_note") or "")
        repo = deps.repos.governance_projection
        manifests = brain.manifests()
        review_rows = _normalize_review_items(payload)
        if not review_rows:
            raise BrainServiceError("review items are required")

        pending_statuses = {"pending_review", "needs_review"}
        review_evidence_template = {
            "review": {
                "decision": decision,
                "reviewed_at": datetime.now(UTC).isoformat(),
                "reviewed_by": actor,
                "review_note": review_note or None,
                "audit_id": audit_id,
            }
        }

        # Phase 1 — 全量 dry-run 校验，零写入；任何校验失败仅记录到 item_result，留待 Phase 3 跳过。
        # apply_groups 同步累计：避免"先写 candidate 再发现 tenant_policy 没法 enable"的 partial state。
        plans: list[dict[str, Any]] = []
        apply_groups: dict[str, dict[str, set[str]]] = {}
        for row in review_rows:
            legacy_system = row["legacy_system"]
            legacy_permission_ref = row["legacy_permission_ref"]
            capability_id = row["capability_id"]
            item_result: dict[str, Any] = {
                "legacy_system": legacy_system,
                "legacy_permission_ref": legacy_permission_ref,
                "capability_id": capability_id,
                "decision": decision,
                "result": "failed",
                "reason": None,
            }
            existing = next(
                (
                    item
                    for item in repo.list_policy_candidates(
                        tenant_id=tenant_id,
                        legacy_system=legacy_system,
                        capability_id=capability_id,
                    )
                    if item.legacy_permission_ref == legacy_permission_ref
                ),
                None,
            )
            if existing is None:
                item_result["reason"] = "candidate_not_found"
                plans.append({"item_result": item_result, "action": "skip"})
                continue

            if decision == "reject":
                if existing.candidate_status not in pending_statuses | {"approved"}:
                    item_result["reason"] = f"invalid_candidate_status:{existing.candidate_status}"
                    plans.append({"item_result": item_result, "action": "skip"})
                    continue
                plans.append({"item_result": item_result, "action": "review", "next_status": "rejected", "existing": existing})
                continue

            if decision == "approve":
                if existing.candidate_status not in pending_statuses:
                    item_result["reason"] = f"invalid_candidate_status:{existing.candidate_status}"
                    plans.append({"item_result": item_result, "action": "skip"})
                    continue
                plans.append({"item_result": item_result, "action": "review", "next_status": "approved", "existing": existing})
                continue

            # apply / approve_and_apply 路径
            if capability_id not in manifests:
                item_result["reason"] = "unmapped_capability"
                plans.append({"item_result": item_result, "action": "skip"})
                continue
            role_ref = str(existing.legacy_role_ref or "")
            if role_ref and role_ref not in policy.ACTOR_NAMES:
                item_result["reason"] = "legacy_role_not_in_product_allowlist"
                plans.append({"item_result": item_result, "action": "skip"})
                continue
            if decision == "apply" and existing.candidate_status != "approved":
                item_result["reason"] = "candidate_not_approved"
                plans.append({"item_result": item_result, "action": "skip"})
                continue
            if decision == "approve_and_apply" and existing.candidate_status not in pending_statuses:
                item_result["reason"] = f"invalid_candidate_status:{existing.candidate_status}"
                plans.append({"item_result": item_result, "action": "skip"})
                continue

            group = apply_groups.setdefault(capability_id, {"role_codes": set(), "surfaces": set()})
            if existing.legacy_role_ref:
                group["role_codes"].add(str(existing.legacy_role_ref))
            if existing.surface:
                group["surfaces"].add(str(existing.surface))
            plans.append(
                {
                    "item_result": item_result,
                    "action": "apply",
                    "existing": existing,
                    "needs_approve_first": decision == "approve_and_apply",
                }
            )

        # Phase 2 — apply_groups 必须 manifest 命中、有 product role；任何一组失败，整批 apply 决策拒绝写入。
        # 校验只读 manifest，无副作用。这样 Phase 3 写入失败的概率收敛到基础设施异常（DB / 磁盘）。
        apply_plans: list[tuple[str, dict[str, Any]]] = []
        if decision in {"apply", "approve_and_apply"}:
            for capability_id, group in apply_groups.items():
                manifest = get_manifest(capability_id)
                product_roles = policy.filter_product_role_codes(sorted(group["role_codes"]))
                if not product_roles:
                    raise BrainServiceError(
                        f"no product role_codes to apply for {capability_id}; abort to avoid partial review state"
                    )
                compatibility = {str(item) for item in (manifest.get("compatibility") or [])}
                surfaces = group["surfaces"]
                exposed_surfaces = sorted(surfaces & compatibility) if surfaces else sorted(compatibility)
                if not exposed_surfaces:
                    exposed_surfaces = ["api"] if "api" in compatibility else sorted(compatibility)[:1]
                if not exposed_surfaces:
                    raise BrainServiceError(
                        f"capability {capability_id} has no compatible surface to expose; abort"
                    )
                apply_plans.append(
                    (
                        capability_id,
                        {
                            "manifest": manifest,
                            "product_roles": product_roles,
                            "exposed_surfaces": exposed_surfaces,
                        },
                    )
                )

        # Phase 3 — 全部校验通过，执行写入。
        results: list[dict[str, Any]] = []
        for plan in plans:
            item_result = plan["item_result"]
            action = plan["action"]
            if action == "skip":
                results.append(item_result)
                continue
            existing = plan["existing"]
            if action == "review":
                record = repo.review_policy_candidate(
                    tenant_id=tenant_id,
                    legacy_system=existing.legacy_system,
                    legacy_permission_ref=existing.legacy_permission_ref,
                    capability_id=existing.capability_id,
                    candidate_status=plan["next_status"],
                    review_evidence=review_evidence_template,
                )
                item_result["result"] = plan["next_status"] if plan["next_status"] != "rejected" else "rejected"
                item_result["candidate_status"] = record.candidate_status
                results.append(item_result)
                continue
            # action == "apply"
            if plan["needs_approve_first"]:
                record = repo.review_policy_candidate(
                    tenant_id=tenant_id,
                    legacy_system=existing.legacy_system,
                    legacy_permission_ref=existing.legacy_permission_ref,
                    capability_id=existing.capability_id,
                    candidate_status="approved",
                    review_evidence=review_evidence_template,
                )
                item_result["candidate_status"] = record.candidate_status
            else:
                item_result["candidate_status"] = "approved"
            item_result["result"] = "approved_and_applied" if plan["needs_approve_first"] else "applied"
            results.append(item_result)

        applied_policies: list[dict[str, Any]] = []
        for capability_id, applied in apply_plans:
            policy_record = deps.repos.capability_package.set_tenant_policy_status(
                {
                    "slug": capability_id,
                    "status": "approved",
                    "source": "governance.policy_candidate.review",
                    "exposure": applied["exposed_surfaces"],
                    "requiresHuman": bool(applied["manifest"].get("human_confirmation_required")),
                    "auditClass": applied["manifest"].get("audit_class"),
                    "tenantPolicy": {"role_codes": applied["product_roles"]},
                },
                tenant_id=tenant_id,
                policy_status="enabled",
                enabled=True,
                exposed_surfaces=applied["exposed_surfaces"],
            )
            applied_policies.append(governance_ser.tenant_policy_to_dict(policy_record))

        failure_count = sum(1 for item in results if item.get("result") == "failed")
        brain._append_audit_feed(
            "governance.policy_candidate.review",
            tenant_id,
            "warning" if failure_count else "ok",
            actor,
        )
        return {
            "tenant_id": tenant_id,
            "decision": decision,
            "items": results,
            "total": len(results),
            "applied_tenant_policies": applied_policies,
            "summary": {
                "success_count": len(results) - failure_count,
                "failure_count": failure_count,
                "applied_policy_count": len(applied_policies),
            },
            "audit_id": audit_id,
        }

    return brain._mutate("governance.policy_candidate.review", role, confirmed, payload, mutation)


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_governance_iam_overview(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _get_governance_iam_overview(brain, payload)

def handler_governance_policy_candidate_list(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _list_policy_mapping_candidates(brain, payload)

def handler_governance_policy_candidate_review(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _review_policy_mapping_candidates(brain, payload)

