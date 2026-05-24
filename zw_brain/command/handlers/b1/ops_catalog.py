"""B1 ops_catalog handlers — 3 cap migrated from BrainService (F1 turn 5).

Method bodies physically migrated (`self.` → `brain.`); per-cap handler functions
registered in `zw_brain.command.dispatch.DISPATCH_TABLE`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService

from zw_brain.domain.repositories.metadata_evidence import MetadataEvidenceRepository
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEFAULT_TENANT_ID = get_runtime_tenant_id()



# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _query_catalog_quality(brain, *, target_type: Any = None, target_ref: Any = None) -> dict[str, Any]:
    store = brain._state_store.database_store
    if store is None:
        return {"items": [], "total": 0}
    items = [
        brain._quality_record_to_dict(item)
        for item in store.metadata_evidence_repo.list_quality_evidence(
            target_type=str(target_type) if target_type else None,
            target_ref=str(target_ref) if target_ref else None,
            tenant_id=_DEFAULT_TENANT_ID,
        )
    ]
    return {"items": items, "total": len(items)}

def _upsert_catalog_quality_evidence(brain, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        store = brain._state_store.database_store
        repo = store.metadata_evidence_repo if store is not None else MetadataEvidenceRepository()
        evidence = repo.upsert_quality_evidence(payload)
        brain._append_audit_feed("ops.catalog.quality.upsert", evidence.quality_ref, "ok", actor)
        return {"quality_ref": evidence.quality_ref, "quality_status": evidence.quality_status, "audit_id": audit_id}

    return brain._mutate("ops.catalog.quality.upsert", role, confirmed, payload, mutation)

def _query_catalog_statistics(brain) -> dict[str, Any]:
    store = brain._state_store.database_store
    if store is None:
        return {
            "summary": {
                "catalogCount": len(brain._snapshot.get("catalog_items", [])),
                "resourceCount": len(brain._snapshot.get("api_resources", [])),
                "schemaMappingCount": 0,
                "qualityEvidenceCount": 0,
                "source_ref": "seed_snapshot",
                "generated_at": brain._now_datetime(),
                "projection_only": True,
            }
        }
    catalog_count = len(store.catalog_repo.list_entries(tenant_id=_DEFAULT_TENANT_ID))
    resource_count = len(store.resource_api_repo.list_assets(tenant_id=_DEFAULT_TENANT_ID))
    schema_mapping_count = len(store.metadata_evidence_repo.list_schema_mappings(tenant_id=_DEFAULT_TENANT_ID))
    quality_count = len(store.metadata_evidence_repo.list_quality_evidence(tenant_id=_DEFAULT_TENANT_ID))
    generated_at = brain._now_datetime()
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

def handler_ops_catalog_quality_query(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _query_catalog_quality(brain, target_type=payload.get("target_type"), target_ref=payload.get("target_ref"))

def handler_ops_catalog_quality_upsert(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _upsert_catalog_quality_evidence(brain, payload)

def handler_ops_catalog_statistics_query(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _query_catalog_statistics(brain)

