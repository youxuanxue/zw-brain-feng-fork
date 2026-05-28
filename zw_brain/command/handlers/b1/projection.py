"""B1 projection handlers — 2 cap migrated from BrainService (F1 turn 5).

Method bodies physically migrated (`self.` → `brain.`); per-cap handler functions
registered in `zw_brain.command.dispatch.DISPATCH_TABLE`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.command.serializers import governance as governance_ser
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _sync_org_projection(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        repo = deps.repos.governance_projection
        tenant = repo.upsert_tenant(payload.get("tenant") or payload)
        tenant_id = tenant.tenant_id
        regions = [repo.upsert_region(item, tenant_id=tenant_id) for item in payload.get("regions") or []]
        orgs_payload = payload.get("orgs") or ([payload] if payload.get("org_code") else [])
        orgs = [repo.upsert_org(item, tenant_id=tenant_id) for item in orgs_payload]
        roles = [repo.upsert_role(item, tenant_id=tenant_id) for item in payload.get("roles") or []]
        deps.append_audit_feed("org.projection.sync", tenant.tenant_id, "ok", actor)
        return {
            "tenant": governance_ser.tenant_projection_to_dict(tenant),
            "orgs": [governance_ser.org_projection_to_dict(item) for item in orgs],
            "regions": [governance_ser.region_projection_to_dict(item) for item in regions],
            "roles": [governance_ser.role_projection_to_dict(item) for item in roles],
            "audit_id": audit_id,
        }

    return deps.write(ctx, payload, mutation)

def _sync_actor_projection(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        repo = deps.repos.governance_projection
        actors_payload = payload.get("actors") or [payload]
        actors: list[Any] = []
        actor_snapshots: list[dict[str, Any]] = []
        for item in actors_payload:
            actor_payload = dict(item)
            claims = actor_payload.get("iaf_claims")
            claims_payload = {}
            tenant_id = str(actor_payload.get("tenant_id", _DEFAULT_TENANT_ID))
            if claims:
                claims_payload = (
                    claims
                    if isinstance(claims, dict)
                    else brain._decode_iaf_claims(claims)
                )
                existing = repo.find_actor_for_iaf_claims(claims_payload, tenant_id=tenant_id)
                actor_payload = actor_payload | brain._build_actor_projection_from_claims(
                    claims=claims,
                    expected_state=actor_payload.get("expected_state"),
                    expected_nonce=actor_payload.get("expected_nonce"),
                    tenant_id=tenant_id,
                    org_code=actor_payload.get("org_code"),
                    fallback_roles=actor_payload.get("role_codes") or actor_payload.get("iam_role_codes") or [],
                    display_name=actor_payload.get("display_name"),
                )
                if existing is not None and not (actor_payload.get("role_codes") or []):
                    role_codes = [str(role) for role in (existing.role_codes_json or [])]
                    if not role_codes:
                        role_codes = sorted(
                            {
                                str(ctx["role_code"])
                                for ctx in repo.list_active_actor_contexts(
                                    tenant_id=tenant_id,
                                    external_actor_id=str(existing.external_actor_id),
                                )
                                if ctx.get("role_code")
                            }
                        )
                    if role_codes:
                        actor_payload["role_codes"] = role_codes
                    if not actor_payload.get("org_code"):
                        actor_payload["org_code"] = existing.org_code
            actor_record = repo.upsert_actor(actor_payload, tenant_id=tenant_id)
            actors.append(actor_record)
            actor_snapshots.append(brain._actor_snapshot_from_projection(actor_record, claims=claims_payload))
        deps.append_audit_feed("actor.projection.sync", actors[0].external_actor_id if actors else "actor_projection", "ok", actor)
        return {
            "items": [governance_ser.actor_projection_to_dict(item) for item in actors],
            "actor_snapshots": actor_snapshots,
            "total": len(actors),
            "audit_id": audit_id,
        }

    return deps.write(ctx, payload, mutation)


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_org_projection_sync(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _sync_org_projection(brain, deps, ctx, payload)

def handler_actor_projection_sync(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _sync_actor_projection(brain, deps, ctx, payload)

