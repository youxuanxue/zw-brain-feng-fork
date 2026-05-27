"""B1 ops_catalog handlers — 3 cap migrated from BrainService (F1 turn 5).

Method bodies physically migrated (`self.` → `brain.`); per-cap handler functions
registered in `zw_brain.command.dispatch.DISPATCH_TABLE`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

import zw_brain.shared.clock as clock
from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.command.serializers import quality as quality_ser
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEFAULT_TENANT_ID = get_runtime_tenant_id()



# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _query_catalog_quality(brain, deps, ctx, *, target_type: Any = None, target_ref: Any = None) -> dict[str, Any]:
    store = deps.state_store.database_store
    if store is None:
        return {"items": [], "total": 0}
    items = [
        quality_ser.quality_to_dict(item)
        for item in deps.repos.metadata_evidence.list_quality_evidence(
            target_type=str(target_type) if target_type else None,
            target_ref=str(target_ref) if target_ref else None,
            tenant_id=_DEFAULT_TENANT_ID,
        )
    ]
    return {"items": items, "total": len(items)}

def _upsert_catalog_quality_evidence(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        repo = deps.repos.metadata_evidence  # Action C — deps.repos always wired (DB or in-memory fallback)
        evidence = repo.upsert_quality_evidence(payload)
        deps.append_audit_feed("ops.catalog.quality.upsert", evidence.quality_ref, "ok", actor)
        return {"quality_ref": evidence.quality_ref, "quality_status": evidence.quality_status, "audit_id": audit_id}

    return deps.write(ctx, payload, mutation)

def _query_catalog_statistics(brain, deps, ctx) -> dict[str, Any]:
    store = deps.state_store.database_store
    if store is None:
        return {
            "summary": {
                "catalogCount": len(deps.brain_legacy._snapshot.get("catalog_items", [])),
                "resourceCount": len(deps.brain_legacy._snapshot.get("api_resources", [])),
                "schemaMappingCount": 0,
                "qualityEvidenceCount": 0,
                "source_ref": "seed_snapshot",
                "generated_at": clock.now_datetime(),
                "projection_only": True,
            }
        }
    catalog_count = len(deps.repos.catalog.list_entries(tenant_id=_DEFAULT_TENANT_ID))
    resource_count = len(deps.repos.resource_api.list_assets(tenant_id=_DEFAULT_TENANT_ID))
    schema_mapping_count = len(deps.repos.metadata_evidence.list_schema_mappings(tenant_id=_DEFAULT_TENANT_ID))
    quality_count = len(deps.repos.metadata_evidence.list_quality_evidence(tenant_id=_DEFAULT_TENANT_ID))
    generated_at = clock.now_datetime()
    source_ref = "canonical_projection"
    return {
        "summary": {
            "catalogCount": catalog_count,
            "resourceCount": resource_count,
            "schemaMappingCount": schema_mapping_count,
            "qualityEvidenceCount": quality_count,
            "source_ref": source_ref,
            "generated_at": generated_at,
            "projection_only": True,
            "evidence": {"source_ref": source_ref, "generated_at": generated_at, "projection_only": True},
        }
    }


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_ops_catalog_quality_query(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _query_catalog_quality(brain, deps, ctx, target_type=payload.get("target_type"), target_ref=payload.get("target_ref"))

def handler_ops_catalog_quality_upsert(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _upsert_catalog_quality_evidence(brain, deps, ctx, payload)

def handler_ops_catalog_statistics_query(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _query_catalog_statistics(brain, deps, ctx)

