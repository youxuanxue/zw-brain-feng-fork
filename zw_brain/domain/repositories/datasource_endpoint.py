from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from zw_brain.domain.models import DatasourceEndpointProjectionRecord
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.sanitization import summary_with_source_kind


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def infer_data_partition(row: dict[str, Any]) -> str:
    display = str(row.get("display_name") or row.get("db_display_name") or "").lower()
    db_name = str(row.get("db_name") or "").lower()
    if "标准" in display or "standard" in db_name:
        return "standard"
    if "服务" in display or "service" in db_name:
        return "service"
    if row.get("node_id") or "前置" in display or "qzk" in db_name:
        return "front"
    if row.get("data_partition") in {"front", "standard", "service"}:
        return str(row["data_partition"])
    return "front"


def endpoint_to_dict(record: DatasourceEndpointProjectionRecord) -> dict[str, Any]:
    summary = record.summary_json if isinstance(record.summary_json, dict) else {}
    return {
        "endpoint_id": record.endpoint_id,
        "connection_ref": record.connection_ref,
        "display_name": record.display_name,
        "db_name": record.db_name,
        "db_type": record.db_type,
        "host": summary.get("host_display") or record.host_ref,
        "port": record.port,
        "org_code": record.org_code,
        "org_name": record.org_name,
        "contact_name": record.contact_name,
        "contact_phone": record.contact_phone,
        "data_partition": record.data_partition,
        "connectivity_status": record.connectivity_status,
        "metadata_database_id": record.metadata_database_id or record.endpoint_id,
        "node_id": record.node_id,
        "node_name": record.node_name,
        "remark": record.remark,
        "source_ref": record.source_ref,
        "resource_origin": "front" if record.data_partition == "front" else "landed",
    }


class DatasourceEndpointRepository:
    def list_endpoints(
        self,
        *,
        tenant_id: str = "sd-default",
        data_partition: str | None = None,
        org_code: str | None = None,
        connectivity_status: str | None = None,
        search: str | None = None,
    ) -> list[DatasourceEndpointProjectionRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            statement = (
                select(DatasourceEndpointProjectionRecord)
                .where(DatasourceEndpointProjectionRecord.tenant_id == tenant_id)
                .order_by(DatasourceEndpointProjectionRecord.display_name)
            )
            if data_partition:
                statement = statement.where(DatasourceEndpointProjectionRecord.data_partition == data_partition)
            if org_code:
                statement = statement.where(DatasourceEndpointProjectionRecord.org_code == org_code)
            if connectivity_status:
                statement = statement.where(
                    DatasourceEndpointProjectionRecord.connectivity_status == connectivity_status
                )
            rows = list(session.execute(statement).scalars())
        if search:
            q = search.strip().lower()
            rows = [
                row
                for row in rows
                if q in (row.display_name or "").lower()
                or q in (row.db_name or "").lower()
                or q in (row.org_name or "").lower()
            ]
        return rows

    def get_endpoint(
        self, endpoint_id: str, *, tenant_id: str = "sd-default"
    ) -> DatasourceEndpointProjectionRecord | None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return session.execute(
                select(DatasourceEndpointProjectionRecord).where(
                    DatasourceEndpointProjectionRecord.tenant_id == tenant_id,
                    DatasourceEndpointProjectionRecord.endpoint_id == endpoint_id,
                )
            ).scalar_one_or_none()

    def upsert_endpoint(self, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> DatasourceEndpointProjectionRecord:
        SessionLocal = create_session_factory()
        endpoint_id = str(payload["endpoint_id"])
        now = _now()
        summary_json = summary_with_source_kind(payload.get("summary_json"), payload.get("source_ref"))
        if payload.get("host_display"):
            summary_json = {**summary_json, "host_display": payload["host_display"]}
        with SessionLocal() as session:
            record = session.execute(
                select(DatasourceEndpointProjectionRecord).where(
                    DatasourceEndpointProjectionRecord.tenant_id == tenant_id,
                    DatasourceEndpointProjectionRecord.endpoint_id == endpoint_id,
                )
            ).scalar_one_or_none()
            partition = infer_data_partition(payload)
            connectivity = str(payload.get("connectivity_status") or "unknown")
            if record is None:
                record = DatasourceEndpointProjectionRecord(
                    tenant_id=tenant_id,
                    endpoint_id=endpoint_id,
                    connection_ref=str(payload.get("connection_ref") or f"datasource:{endpoint_id}"),
                    display_name=str(payload.get("display_name") or payload.get("db_display_name") or endpoint_id),
                    db_name=str(payload.get("db_name") or ""),
                    db_type=str(payload.get("db_type") or "mysql"),
                    host_ref=payload.get("host_ref"),
                    port=payload.get("port"),
                    org_code=payload.get("org_code"),
                    org_name=payload.get("org_name"),
                    contact_name=payload.get("contact_name") or payload.get("db_linkname"),
                    contact_phone=payload.get("contact_phone") or payload.get("db_linkphone"),
                    data_partition=partition,
                    connectivity_status=connectivity,
                    secret_ref=payload.get("secret_ref"),
                    metadata_database_id=str(payload.get("metadata_database_id") or endpoint_id),
                    node_id=payload.get("node_id"),
                    node_name=payload.get("node_name"),
                    remark=payload.get("remark") or payload.get("db_desc"),
                    source_ref=payload.get("source_ref"),
                    summary_json=summary_json,
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)
            else:
                record.display_name = str(payload.get("display_name") or record.display_name)
                record.db_name = str(payload.get("db_name") or record.db_name)
                record.db_type = str(payload.get("db_type") or record.db_type)
                if payload.get("host_ref") is not None:
                    record.host_ref = payload.get("host_ref")
                if payload.get("port") is not None:
                    record.port = payload.get("port")
                record.org_code = payload.get("org_code", record.org_code)
                record.org_name = payload.get("org_name", record.org_name)
                record.contact_name = payload.get("contact_name", record.contact_name)
                record.contact_phone = payload.get("contact_phone", record.contact_phone)
                record.data_partition = partition
                record.connectivity_status = connectivity
                if payload.get("secret_ref"):
                    record.secret_ref = payload.get("secret_ref")
                record.metadata_database_id = str(payload.get("metadata_database_id") or record.metadata_database_id)
                record.node_id = payload.get("node_id", record.node_id)
                record.node_name = payload.get("node_name", record.node_name)
                record.remark = payload.get("remark", record.remark)
                record.source_ref = payload.get("source_ref", record.source_ref)
                record.summary_json = summary_json
                record.updated_at = now
            session.commit()
            session.refresh(record)
            return record

    def delete_endpoint(self, endpoint_id: str, *, tenant_id: str = "sd-default") -> bool:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(
                select(DatasourceEndpointProjectionRecord).where(
                    DatasourceEndpointProjectionRecord.tenant_id == tenant_id,
                    DatasourceEndpointProjectionRecord.endpoint_id == endpoint_id,
                )
            ).scalar_one_or_none()
            if record is None:
                return False
            session.delete(record)
            session.commit()
            return True
