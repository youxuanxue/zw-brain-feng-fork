"""J2 metadata handlers — 8 cap migrated from BrainService (F1 turn 4).

Method bodies physically migrated; `self.` → `brain.` substitution applied. Per-cap handler
functions registered in `zw_brain.command.dispatch.DISPATCH_TABLE`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService

from zw_brain.command.serializers import metadata as metadata_ser
from zw_brain.domain.repositories.metadata_evidence import MetadataEvidenceRepository
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEFAULT_TENANT_ID = get_runtime_tenant_id()


# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _discover_metadata_schema(brain, payload: dict[str, Any]) -> dict[str, Any]:
    """List ResourceSchemaSnapshotRecord rows that don't yet have a reverse draft."""
    from sqlalchemy import desc, select  # noqa: PLC0415

    from zw_brain.domain.models import (  # noqa: PLC0415
        CatalogEntryRecord,
        ResourceSchemaSnapshotRecord,
    )
    from zw_brain.shared.db import create_session_factory  # noqa: PLC0415

    tenant_id = str(payload.get("tenant_id") or _DEFAULT_TENANT_ID)
    limit = max(1, min(int(payload.get("limit") or 50), 200))
    SessionLocal = create_session_factory()
    with SessionLocal() as session:
        snapshots = session.execute(
            select(ResourceSchemaSnapshotRecord)
            .where(ResourceSchemaSnapshotRecord.tenant_id == tenant_id)
            .order_by(desc(ResourceSchemaSnapshotRecord.created_at))
            .limit(limit)
        ).scalars().all()
        # full-scan-ok: summary_json.source 是 JSON 列上的 reverse-source 过滤；
        # 等同于 supply_demand.list_demands 的 JSON 维度场景；当前 catalog ≤ 1.2 万行，
        # trigger: catalog 5 万级或多租户 → 把 source 提到独立索引列（D7 adapter 输入归口）。
        # 详见 docs/preflight-debt.md 「2026-05-26 — 读路径热表 tenant-only 全扫白名单」
        existing_reverse = {
            (entry.summary_json or {}).get("schema_ref")
            for entry in session.execute(
                select(CatalogEntryRecord).where(CatalogEntryRecord.tenant_id == tenant_id)
            ).scalars().all()
            if isinstance(entry.summary_json, dict) and entry.summary_json.get("source") == "reverse"
        }
    items = [
        {
            "schema_ref": snap.snapshot_ref,
            "resource_code": snap.resource_code,
            "binding_code": snap.binding_code,
            "captured_at": snap.captured_at.isoformat() if snap.captured_at else None,
            "has_reverse_draft": snap.snapshot_ref in existing_reverse,
        }
        for snap in snapshots
    ]
    return {"items": items, "total": len(items)}

def _query_metadata_schema(brain, *, resource_code: Any = None, binding_code: Any = None) -> dict[str, Any]:
    store = brain._state_store.database_store
    if store is None:
        return {"items": [], "total": 0}
    items = [
        metadata_ser.schema_snapshot_to_dict(item)
        for item in store.metadata_evidence_repo.list_schema_snapshots(
            resource_code=str(resource_code) if resource_code else None,
            binding_code=str(binding_code) if binding_code else None,
            tenant_id=_DEFAULT_TENANT_ID,
        )
    ]
    return {"items": items, "total": len(items)}

def _query_metadata_catalog_items(brain, *, resource_code: Any = None, catalog_code: Any = None, include_inactive: Any = True) -> dict[str, Any]:
    store = brain._state_store.database_store
    if store is None:
        return {"items": [], "total": 0, "summary": brain._mapping_diagnostics([])["summary"], "catalogFields": []}
    catalog_code_text = str(catalog_code) if catalog_code else None
    diagnostics = brain._mapping_diagnostics(
        store.metadata_evidence_repo.list_schema_mappings(
            resource_code=str(resource_code) if resource_code else None,
            catalog_code=catalog_code_text,
            include_inactive=str(include_inactive).lower() not in {"false", "0", "no"},
            tenant_id=_DEFAULT_TENANT_ID,
        ),
        store=store,
    )
    if catalog_code_text:
        catalog_fields = brain._catalog_field_dicts(catalog_code_text, store)
        for item in diagnostics["items"]:
            if item.get("catalog_item_title"):
                continue
            matched = next((field for field in catalog_fields if field["item_code"] == item.get("catalog_item_code")), None)
            if matched:
                item["catalog_item_title"] = matched["title"]
                item["catalog_item_summary"] = matched["summary_json"]
        if catalog_fields and not diagnostics["items"]:
            diagnostics["summary"] = diagnostics["summary"] | {
                "catalog_fields": len(catalog_fields),
                "diagnosis": "catalog_fields_only",
            }
        return diagnostics | {"total": len(diagnostics["items"]), "catalogFields": catalog_fields}
    return diagnostics | {"total": len(diagnostics["items"]), "catalogFields": []}

def _query_metadata_lineage(brain, *, resource_code: Any = None, relation_scope: Any = None) -> dict[str, Any]:
    store = brain._state_store.database_store
    if store is None:
        return {"items": [], "total": 0}
    items = [
        metadata_ser.lineage_to_dict(item)
        for item in store.metadata_evidence_repo.list_lineage_relations(
            resource_code=str(resource_code) if resource_code else None,
            relation_scope=str(relation_scope) if relation_scope else None,
            tenant_id=_DEFAULT_TENANT_ID,
        )
    ]
    return {"items": items, "total": len(items)}

def _query_metadata_gather_evidence(brain, *, resource_code: Any = None, status: Any = None) -> dict[str, Any]:
    store = brain._state_store.database_store
    if store is None:
        return {"items": [], "total": 0}
    items = [
        metadata_ser.gather_evidence_to_dict(item)
        for item in store.metadata_evidence_repo.list_gather_evidence(
            resource_code=str(resource_code) if resource_code else None,
            status=str(status) if status else None,
            tenant_id=_DEFAULT_TENANT_ID,
        )
    ]
    return {"items": items, "total": len(items)}

def _upsert_metadata_schema_snapshot(brain, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        store = brain._state_store.database_store
        repo = store.metadata_evidence_repo if store is not None else MetadataEvidenceRepository()
        snapshot = repo.upsert_schema_snapshot(payload)
        brain._append_audit_feed("metadata.schema.snapshot.upsert", snapshot.snapshot_ref, "ok", actor)
        return {"snapshot_ref": snapshot.snapshot_ref, "schema_hash": snapshot.schema_hash, "audit_id": audit_id}

    return brain._mutate("metadata.schema.snapshot.upsert", role, confirmed, payload, mutation)

def _upsert_metadata_gather_evidence(brain, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        store = brain._state_store.database_store
        repo = store.metadata_evidence_repo if store is not None else MetadataEvidenceRepository()
        evidence = repo.upsert_gather_evidence(payload)
        brain._append_audit_feed("metadata.gather.evidence.upsert", evidence.gather_task_ref, "ok", actor)
        return {"gather_task_ref": evidence.gather_task_ref, "status": evidence.status, "audit_id": audit_id}

    return brain._mutate("metadata.gather.evidence.upsert", role, confirmed, payload, mutation)

def _upsert_metadata_lineage(brain, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        store = brain._state_store.database_store
        repo = store.metadata_evidence_repo if store is not None else MetadataEvidenceRepository()
        relation = repo.upsert_lineage_relation(payload)
        brain._append_audit_feed("metadata.lineage.upsert", relation.relation_ref, "ok", actor)
        return {"relation_ref": relation.relation_ref, "relation_type": relation.relation_type, "audit_id": audit_id}

    return brain._mutate("metadata.lineage.upsert", role, confirmed, payload, mutation)


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_metadata_schema_discover(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _discover_metadata_schema(brain, payload)

def handler_metadata_schema_query(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _query_metadata_schema(brain, resource_code=payload.get("resource_code"), binding_code=payload.get("binding_code"))

def handler_metadata_catalog_item_query(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _query_metadata_catalog_items(brain, resource_code=payload.get("resource_code"), catalog_code=payload.get("catalog_code"), include_inactive=payload.get("include_inactive", True))

def handler_metadata_lineage_query(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _query_metadata_lineage(brain, resource_code=payload.get("resource_code"), relation_scope=payload.get("relation_scope"))

def handler_metadata_gather_evidence_query(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _query_metadata_gather_evidence(brain, resource_code=payload.get("resource_code"), status=payload.get("status"))

def handler_metadata_schema_snapshot_upsert(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _upsert_metadata_schema_snapshot(brain, payload)

def handler_metadata_gather_evidence_upsert(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _upsert_metadata_gather_evidence(brain, payload)

def handler_metadata_lineage_upsert(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _upsert_metadata_lineage(brain, payload)

