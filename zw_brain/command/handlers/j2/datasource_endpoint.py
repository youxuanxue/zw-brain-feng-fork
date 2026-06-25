"""J2 数据源 endpoint 投影 handlers — 数据源管理 / 反向编目 / 挂接前置。"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from sqlalchemy import desc, select

from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.domain.models import ResourceSchemaSnapshotRecord
from zw_brain.domain.repositories.datasource_endpoint import DatasourceEndpointRepository, endpoint_to_dict
from zw_brain.domain.services.reference_service import ReferenceService
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID


def _tenant(payload: dict[str, Any]) -> str:
    return str(payload.get("tenant_id") or _DEFAULT_TENANT_ID)


def _repo(deps: HandlerDeps) -> DatasourceEndpointRepository:
    return deps.repos.datasource_endpoint


def _list_endpoints(_brain, deps, _ctx, payload: dict[str, Any]) -> dict[str, Any]:
    repo = _repo(deps)
    rows = repo.list_endpoints(
        tenant_id=_tenant(payload),
        data_partition=str(payload["data_partition"]) if payload.get("data_partition") else None,
        org_code=str(payload["org_code"]) if payload.get("org_code") else None,
        connectivity_status=str(payload["connectivity_status"]) if payload.get("connectivity_status") else None,
        search=str(payload["search"]) if payload.get("search") else None,
    )
    org_name = ReferenceService().org_name_resolver(tenant_id=_tenant(payload))
    items = [endpoint_to_dict(row, org_name_resolver=org_name) for row in rows if row.connectivity_status != "deleted"]
    return {"items": items, "total": len(items)}


def _upsert_endpoint(_brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    import uuid

    endpoint_id = str(payload.get("endpoint_id") or uuid.uuid4().hex)

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        repo = _repo(deps)
        body = dict(payload)
        body["endpoint_id"] = endpoint_id
        if not body.get("connection_ref"):
            body["connection_ref"] = f"manual:datasource:{endpoint_id}"
        if body.get("connectivity_status") is None:
            body["connectivity_status"] = "unknown"
        record = repo.upsert_endpoint(body, tenant_id=_tenant(payload))
        deps.append_audit_feed("datasource.endpoint.upsert", endpoint_id, "ok", actor)
        org_name = ReferenceService().org_name_resolver(tenant_id=_tenant(payload))
        return {"endpoint": endpoint_to_dict(record, org_name_resolver=org_name), "audit_id": audit_id}

    return deps.write(ctx, payload, mutation)


def _delete_endpoint(_brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    endpoint_id = str(payload["endpoint_id"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        deleted = _repo(deps).delete_endpoint(endpoint_id, tenant_id=_tenant(payload))
        deps.append_audit_feed("datasource.endpoint.delete", endpoint_id, "ok" if deleted else "missing", actor)
        return {"endpoint_id": endpoint_id, "deleted": deleted, "audit_id": audit_id}

    return deps.write(ctx, payload, mutation)


def _test_connectivity(_brain, deps, _ctx, payload: dict[str, Any]) -> dict[str, Any]:
    endpoint_id = str(payload.get("endpoint_id") or payload.get("connection_ref", "")).split(":")[-1]
    record = _repo(deps).get_endpoint(endpoint_id, tenant_id=_tenant(payload))
    if record is None:
        return {
            "endpoint_id": endpoint_id,
            "status": "not_found",
            "latency_ms": 0,
            "error_summary": "数据源不存在",
        }
    status = record.connectivity_status
    if status == "unknown":
        status = "disconnected"
    return {
        "endpoint_id": record.endpoint_id,
        "connection_ref": record.connection_ref,
        "status": "ok" if status == "connected" else "failed",
        "connectivity_status": status,
        "latency_ms": 1 if status == "connected" else 0,
        "error_summary": None if status == "connected" else "数据源未连通（导入态快照）",
    }


def _list_tables(_brain, deps, _ctx, payload: dict[str, Any]) -> dict[str, Any]:
    tenant_id = _tenant(payload)
    metadata_db_id = str(payload.get("metadata_database_id") or payload.get("endpoint_id") or "")
    search = str(payload.get("search") or "").strip().lower()
    limit = max(1, min(int(payload.get("limit") or 200), 500))
    SessionLocal = create_session_factory()
    with SessionLocal() as session:
        snapshots = session.execute(
            select(ResourceSchemaSnapshotRecord)
            .where(ResourceSchemaSnapshotRecord.tenant_id == tenant_id)
            .where(ResourceSchemaSnapshotRecord.snapshot_ref.like("%:db_meta_table:%"))
            .order_by(desc(ResourceSchemaSnapshotRecord.captured_at))
            .limit(2000)
        ).scalars().all()
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for snap in snapshots:
        schema = snap.schema_json if isinstance(snap.schema_json, dict) else {}
        db_meta_id = str(schema.get("database_meta_id") or "")
        if metadata_db_id and db_meta_id != metadata_db_id:
            continue
        table_meta_id = str(schema.get("meta_id") or snap.resource_code or "")
        if not table_meta_id or table_meta_id in seen:
            continue
        table_name = str(schema.get("table_name") or table_meta_id)
        if search and search not in table_name.lower() and search not in str(schema.get("comment") or "").lower():
            continue
        seen.add(table_meta_id)
        items.append(
            {
                "table_meta_id": table_meta_id,
                "table_name": table_name,
                "table_comment": schema.get("comment") or schema.get("remark") or "",
                "schema_ref": snap.snapshot_ref,
                "database_meta_id": db_meta_id or metadata_db_id,
            }
        )
        if len(items) >= limit:
            break
    return {"items": items, "total": len(items)}


def _list_table_columns(_brain, deps, _ctx, payload: dict[str, Any]) -> dict[str, Any]:
    tenant_id = _tenant(payload)
    table_meta_id = str(payload.get("table_meta_id") or payload.get("schema_ref", "").split(":")[-1])
    SessionLocal = create_session_factory()
    with SessionLocal() as session:
        snapshots = session.execute(
            select(ResourceSchemaSnapshotRecord)
            .where(ResourceSchemaSnapshotRecord.tenant_id == tenant_id)
            .where(ResourceSchemaSnapshotRecord.resource_code == table_meta_id)
            .where(ResourceSchemaSnapshotRecord.snapshot_ref.like("%:db_meta_column:%"))
            .order_by(ResourceSchemaSnapshotRecord.snapshot_ref)
        ).scalars().all()
    items: list[dict[str, Any]] = []
    for snap in snapshots:
        schema = snap.schema_json if isinstance(snap.schema_json, dict) else {}
        items.append(
            {
                "column_name": schema.get("column_name") or schema.get("name") or "",
                "comment": schema.get("comment") or schema.get("remark") or "",
                "data_type": schema.get("format") or schema.get("data_type") or "",
                "length": schema.get("length"),
                "is_pk": schema.get("is_pk"),
                "is_null": schema.get("is_null"),
                "schema_ref": snap.snapshot_ref,
            }
        )
    return {"items": items, "total": len(items)}


def handler_datasource_endpoint_list(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    return _list_endpoints(deps.brain_legacy, deps, ctx, payload)


def handler_datasource_endpoint_upsert(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    return _upsert_endpoint(deps.brain_legacy, deps, ctx, payload)


def handler_datasource_endpoint_delete(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    return _delete_endpoint(deps.brain_legacy, deps, ctx, payload)


def handler_datasource_connectivity_test(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    return _test_connectivity(deps.brain_legacy, deps, ctx, payload)


def handler_datasource_table_list(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    return _list_tables(deps.brain_legacy, deps, ctx, payload)


def handler_datasource_table_columns(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    return _list_table_columns(deps.brain_legacy, deps, ctx, payload)
