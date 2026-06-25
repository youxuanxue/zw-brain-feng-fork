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

from zw_brain.capability_registry.runtime import get_manifest
from zw_brain.command.brain import BrainServiceError, _count_by
from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.command.serializers import adapter as adapter_ser
from zw_brain.command.serializers import governance as governance_ser
from zw_brain.domain import policy
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID
from zw_brain.shared.sanitization import safe_json

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _get_governance_iam_overview(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    tenant_id = str(payload.get("tenant_id", _DEFAULT_TENANT_ID))
    status_filter = str(payload.get("binding_status", payload.get("status", "")) or "")
    capability_filter = str(payload.get("capability_id", payload.get("capability_slug", "")) or "")
    issue_filter = str(payload.get("issue_type", "") or "")
    repo = deps.repos.governance_projection
    store = deps.state_store.database_store
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
    actors = [item for item in actors if deps.services.governance.filter_actor(item, status_filter=status_filter, role_filter=role_filter, actor_filter=actor_filter)]
    policies = [governance_ser.tenant_policy_to_dict(item) for item in deps.repos.capability_package.list_policies(tenant_id=tenant_id)] if store is not None else []
    if capability_filter:
        policies = [item for item in policies if item.get("package_slug") == capability_filter]
    candidates = [governance_ser.legacy_policy_candidate_to_dict(item) for item in repo.list_policy_candidates(tenant_id=tenant_id)]
    if capability_filter:
        candidates = [item for item in candidates if item.get("capability_id") == capability_filter]
    adapter_runs = [adapter_ser.adapter_run_to_dict(item) for item in deps.repos.external_adapter.list_run_records(tenant_id=tenant_id, adapter_slug="legacy.bsp.governance")]
    issues = deps.services.governance.import_issues(adapter_runs)
    if issue_filter:
        issues = [item for item in issues if item.get("type") == issue_filter]
    audit_events = deps.services.governance.audit_events(tenant_id=tenant_id, capability_filter=capability_filter, actor_filter=actor_filter)
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
                "role": str(payload.get("role", (actor_snapshot.get("role_codes") or [ctx.role])[0])),
                "actor_snapshot": actor_snapshot,
                "org_snapshot": copy.deepcopy(sample_org or {}),
                "risk_context": safe_json(payload.get("risk_context") or {}),
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

def _list_policy_mapping_candidates(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
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

def _review_policy_mapping_candidates(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    role = str(payload.get("role", ctx.role))
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
            # scan-to-one-ok: list_policy_candidates 已按 tenant+legacy_system+capability_id 三维 SQL 下推，残余按 permission_ref 选一条为有界小集，非全表扫
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
        deps.append_audit_feed(
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

    return deps.write(ctx, payload, mutation)


# ──────────────────────────────────────────────────────────────────────────
# D62 — In-product role governance (actor list / assign / revoke / status / matrix).
# zw-brain owns authorization; these are the admin-facing read + write surfaces.
# ──────────────────────────────────────────────────────────────────────────

def _list_actors(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    deps = brain._get_handler_deps()
    tenant_id = str(payload.get("tenant_id", _DEFAULT_TENANT_ID))
    q = str(payload.get("q") or "").strip().lower()
    # org_filter (NOT org_code): the trusted BFF path overwrites payload.org_code with the
    # caller's own org, which would silently restrict a ROLE_SYSTEM admin to only their own org's
    # actors. Read the explicit, non-clobbered filter field instead.
    org_filter = str(payload.get("org_filter") or "").strip()
    role_filter = str(payload.get("role_code") or "").strip()
    status_filter = str(payload.get("status") or "").strip()
    repo = deps.repos.governance_projection
    org_names = {
        str(org.org_code or ""): str(org.org_name or "")
        for org in repo.list_orgs(tenant_id=tenant_id)
    }

    def org_name(code: object) -> str:
        return org_names.get(str(code or "").strip(), "")

    def org_matches(code: object) -> bool:
        if not org_filter:
            return True
        raw_code = str(code or "")
        name = org_name(raw_code)
        needle = org_filter.lower()
        return needle in raw_code.lower() or needle in name.lower()

    actors = repo.list_actors(tenant_id=tenant_id)
    active_bindings = repo.list_actor_org_role_bindings(tenant_id=tenant_id, binding_status="active")
    bindings_by_actor: dict[str, list[Any]] = {}
    for binding in active_bindings:
        bindings_by_actor.setdefault(binding.external_actor_id, []).append(binding)
    status_counts: dict[str, int] = {}
    items: list[dict[str, Any]] = []
    for actor in actors:
        status_counts[actor.status] = status_counts.get(actor.status, 0) + 1
        item = governance_ser.actor_with_bindings_to_dict(actor, bindings_by_actor.get(actor.external_actor_id, []))
        # 身份治理是 ROLE_SYSTEM 独占的用户管理面；用户行必须可识别。只放开列表展示名，
        # profile_json 仍走 serializer 默认脱敏，不外放手机号/邮箱/证件号等字段。
        item["display_name"] = actor.display_name
        item["org_name"] = org_name(actor.org_code)
        for bd in item.get("bindings", []):
            bd["org_name"] = org_name(bd.get("org_code"))
        if status_filter and item.get("status") != status_filter:
            continue
        binding_orgs = {bd.get("org_code") for bd in item.get("bindings", [])}
        binding_roles = {bd.get("role_code") for bd in item.get("bindings", [])}
        if org_filter and not org_matches(item.get("org_code")) and not any(org_matches(code) for code in binding_orgs):
            continue
        if role_filter and role_filter not in binding_roles:
            continue
        if q:
            # Match against the raw record fields; this ROLE_SYSTEM-only management list shows
            # display_name, while profile_json remains serializer-masked.
            profile = actor.profile_json if isinstance(actor.profile_json, dict) else {}
            haystack = " ".join(
                str(v or "")
                for v in (
                    actor.display_name,
                    actor.external_actor_id,
                    actor.org_code,
                    org_name(actor.org_code),
                    *(bd.get("org_code") for bd in item.get("bindings", [])),
                    *(bd.get("org_name") for bd in item.get("bindings", [])),
                    profile.get("account"),
                )
            ).lower()
            if q not in haystack:
                continue
        items.append(item)
    return {
        "tenant_id": tenant_id,
        "total": len(items),
        "items": items,
        "summary": {"total": len(actors), "status_counts": status_counts},
    }


def _access_matrix(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    from zw_brain.domain import role_codes as _role_codes

    def _cap(permission: str) -> str:
        return permission[: -len(".execute")] if permission.endswith(".execute") else permission

    roles: list[dict[str, Any]] = []
    cap_to_roles: dict[str, set[str]] = {}
    for role_code, display_name in _role_codes.ROLE_DISPLAY_NAMES_ZH.items():
        capabilities = sorted({_cap(perm) for perm in policy.permissions_for_role(role_code)})
        roles.append(
            {
                "role_code": role_code,
                "display_name": display_name,
                "capability_count": len(capabilities),
                "capabilities": capabilities,
            }
        )
        for capability_id in capabilities:
            cap_to_roles.setdefault(capability_id, set()).add(role_code)
    capabilities = [
        {"capability_id": capability_id, "roles": sorted(role_set)}
        for capability_id, role_set in sorted(cap_to_roles.items())
    ]
    return {"roles": roles, "capabilities": capabilities}


def _assign_actor_role(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    deps = brain._get_handler_deps()

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        tenant_id = str(payload.get("tenant_id", _DEFAULT_TENANT_ID))
        external_actor_id = str(payload.get("external_actor_id") or "").strip()
        # Target binding org: use the dedicated `target_org_code` field, NOT `org_code` —
        # the trusted-session BFF path overwrites payload["org_code"] with the CALLER's session
        # org (D61 caller-context), which would silently bind the role in the admin's own org
        # instead of the target's. Fall back to the target actor's home org when unspecified.
        target_org_code = str(payload.get("target_org_code") or "").strip()
        role_code = str(payload.get("role_code") or "").strip()
        note = str(payload.get("note") or "")
        from zw_brain.domain import role_codes as _role_codes

        if not external_actor_id or not role_code:
            raise BrainServiceError("external_actor_id, role_code are required")
        # R-003: only the fixed product role catalog (5 业务角色 + ROLE_SYSTEM) is assignable;
        # internal SYSTEM_ROLE_CODES (admin/system) are never granted to people (D62). The UI
        # constrains this, but the backend is the security boundary for direct REST/CLI/A2A.
        if role_code not in _role_codes.BUSINESS_ROLE_CODES:
            raise BrainServiceError(f"role_code not assignable: {role_code}")
        repo = deps.repos.governance_projection
        target = repo.get_actor(external_actor_id, tenant_id=tenant_id)
        if target is None:
            raise BrainServiceError(f"unknown actor: {external_actor_id}")
        if target.status == "disabled":
            raise BrainServiceError("cannot assign a role to a disabled actor; enable it first")
        org_code = target_org_code or str(target.org_code or "")
        if not org_code:
            raise BrainServiceError("target_org_code is required (target actor has no home org)")
        # R-005: defense-in-depth — don't write a binding to a dangling org_code (no FK on the
        # column by D48 §2.5 honest-downgrade). Mirrors the unknown-actor guard above.
        if repo.get_org_by_code(org_code, tenant_id=tenant_id) is None:
            raise BrainServiceError(f"unknown org_code: {org_code}")
        binding = repo.assign_actor_role(
            external_actor_id=external_actor_id,
            org_code=org_code,
            role_code=role_code,
            tenant_id=tenant_id,
            granted_by=actor,
            note=note,
        )
        deps.append_audit_feed("governance.actor.role.assign", external_actor_id, "ok", actor)
        return {
            "ok": True,
            "audit_id": audit_id,
            "external_actor_id": external_actor_id,
            "org_code": org_code,
            "role_code": role_code,
            "binding_status": binding.binding_status,
        }

    return deps.write(ctx, payload, mutation)


def _revoke_actor_role(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    deps = brain._get_handler_deps()

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        tenant_id = str(payload.get("tenant_id", _DEFAULT_TENANT_ID))
        external_actor_id = str(payload.get("external_actor_id") or "").strip()
        # See assign: `org_code` is clobbered by the trusted BFF path with the caller's org, so a
        # revoke keyed on it would target the wrong (admin's) org and silently miss. Use the
        # dedicated target_org_code (the binding's own org from the UI chip), fall back to the
        # target actor's home org.
        target_org_code = str(payload.get("target_org_code") or "").strip()
        role_code = str(payload.get("role_code") or "").strip()
        if not external_actor_id or not role_code:
            raise BrainServiceError("external_actor_id, role_code are required")
        repo = deps.repos.governance_projection
        org_code = target_org_code
        if not org_code:
            target = repo.get_actor(external_actor_id, tenant_id=tenant_id)
            org_code = str(target.org_code or "") if target is not None else ""
        if not org_code:
            raise BrainServiceError("target_org_code is required (target actor has no home org)")
        revoked = repo.revoke_actor_role(
            external_actor_id=external_actor_id,
            org_code=org_code,
            role_code=role_code,
            tenant_id=tenant_id,
        )
        deps.append_audit_feed("governance.actor.role.revoke", external_actor_id, "ok" if revoked else "warning", actor)
        return {
            "ok": True,
            "audit_id": audit_id,
            "revoked": revoked,
            "external_actor_id": external_actor_id,
            "org_code": org_code,
            "role_code": role_code,
        }

    return deps.write(ctx, payload, mutation)


def _set_actor_status(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    deps = brain._get_handler_deps()

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        tenant_id = str(payload.get("tenant_id", _DEFAULT_TENANT_ID))
        external_actor_id = str(payload.get("external_actor_id") or "").strip()
        status = str(payload.get("status") or "").strip()
        if not external_actor_id:
            raise BrainServiceError("external_actor_id is required")
        if status not in {"active", "disabled"}:
            raise BrainServiceError(f"unsupported actor status: {status!r}")
        repo = deps.repos.governance_projection
        record = repo.set_actor_status(external_actor_id=external_actor_id, status=status, tenant_id=tenant_id)
        if record is None:
            raise BrainServiceError(f"unknown actor: {external_actor_id}")
        deps.append_audit_feed("governance.actor.status.set", external_actor_id, "ok", actor)
        return {"ok": True, "audit_id": audit_id, "external_actor_id": external_actor_id, "status": record.status}

    return deps.write(ctx, payload, mutation)


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_governance_iam_overview(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _get_governance_iam_overview(brain, deps, ctx, payload)

def handler_governance_policy_candidate_list(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _list_policy_mapping_candidates(brain, deps, ctx, payload)

def handler_governance_policy_candidate_review(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _review_policy_mapping_candidates(brain, deps, ctx, payload)

def handler_governance_actor_list(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None
    return _list_actors(brain, deps, ctx, payload)

def handler_governance_access_matrix(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None
    return _access_matrix(brain, deps, ctx, payload)

def handler_governance_actor_role_assign(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None
    return _assign_actor_role(brain, deps, ctx, payload)

def handler_governance_actor_role_revoke(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None
    return _revoke_actor_role(brain, deps, ctx, payload)

def handler_governance_actor_status_set(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None
    return _set_actor_status(brain, deps, ctx, payload)
