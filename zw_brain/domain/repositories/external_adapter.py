from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from zw_brain.domain.models import AdapterRunRecord, ExternalObjectMappingRecord
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.sanitization import safe_json


def _now() -> datetime:
    return datetime.now(UTC)


class ExternalAdapterRepository:
    def upsert_mapping(self, payload: dict[str, Any], *, tenant_id: str = "default") -> ExternalObjectMappingRecord:
        mapping = self._mapping_payload(payload, tenant_id=tenant_id)
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(
                select(ExternalObjectMappingRecord).where(
                    ExternalObjectMappingRecord.tenant_id == mapping["tenant_id"],
                    ExternalObjectMappingRecord.external_system == mapping["external_system"],
                    ExternalObjectMappingRecord.direction == mapping["direction"],
                    ExternalObjectMappingRecord.local_aggregate_type == mapping["local_aggregate_type"],
                    ExternalObjectMappingRecord.local_aggregate_id == mapping["local_aggregate_id"],
                    ExternalObjectMappingRecord.external_object_type == mapping["external_object_type"],
                    ExternalObjectMappingRecord.external_object_id == mapping["external_object_id"],
                )
            ).scalar_one_or_none()
            if record is None:
                record = ExternalObjectMappingRecord(**mapping)
                session.add(record)
                session.flush()
            else:
                record.legacy_table = mapping["legacy_table"]
                record.legacy_id = mapping["legacy_id"]
                record.protocol_version = mapping["protocol_version"]
                record.batch_no = mapping["batch_no"]
                record.status = mapping["status"]
                record.last_receipt_json = mapping["last_receipt_json"]
                record.extra_json = mapping["extra_json"]
                record.updated_at = _now()
            session.commit()
            return session.execute(select(ExternalObjectMappingRecord).where(ExternalObjectMappingRecord.id == record.id)).scalar_one()

    def list_mappings(
        self,
        *,
        tenant_id: str = "default",
        external_system: str | None = None,
        local_aggregate_type: str | None = None,
        local_aggregate_id: str | None = None,
        status: str | None = None,
    ) -> list[ExternalObjectMappingRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            statement = select(ExternalObjectMappingRecord).where(ExternalObjectMappingRecord.tenant_id == tenant_id)
            if external_system:
                statement = statement.where(ExternalObjectMappingRecord.external_system == external_system)
            if local_aggregate_type:
                statement = statement.where(ExternalObjectMappingRecord.local_aggregate_type == local_aggregate_type)
            if local_aggregate_id:
                statement = statement.where(ExternalObjectMappingRecord.local_aggregate_id == local_aggregate_id)
            if status:
                statement = statement.where(ExternalObjectMappingRecord.status == status)
            return list(session.execute(statement.order_by(ExternalObjectMappingRecord.updated_at)).scalars())

    def upsert_run_record(self, payload: dict[str, Any], *, tenant_id: str = "default") -> AdapterRunRecord:
        record_payload = self._run_payload(payload, tenant_id=tenant_id)
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(
                select(AdapterRunRecord).where(
                    AdapterRunRecord.tenant_id == record_payload["tenant_id"],
                    AdapterRunRecord.adapter_slug == record_payload["adapter_slug"],
                    AdapterRunRecord.operation == record_payload["operation"],
                    AdapterRunRecord.idempotency_key == record_payload["idempotency_key"],
                )
            ).scalar_one_or_none()
            if record is None:
                record = AdapterRunRecord(**record_payload)
                session.add(record)
                session.flush()
            else:
                record.direction = record_payload["direction"]
                record.source_ref = record_payload["source_ref"]
                record.status = record_payload["status"]
                record.target_count = record_payload["target_count"]
                record.success_count = record_payload["success_count"]
                record.failure_count = record_payload["failure_count"]
                record.receipt_json = record_payload["receipt_json"]
                record.error_summary = record_payload["error_summary"]
                record.finished_at = record_payload["finished_at"]
                record.updated_at = _now()
            session.commit()
            return session.execute(select(AdapterRunRecord).where(AdapterRunRecord.id == record.id)).scalar_one()

    def list_run_records(
        self,
        *,
        tenant_id: str = "default",
        adapter_slug: str | None = None,
        operation: str | None = None,
        status: str | None = None,
    ) -> list[AdapterRunRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            statement = select(AdapterRunRecord).where(AdapterRunRecord.tenant_id == tenant_id)
            if adapter_slug:
                statement = statement.where(AdapterRunRecord.adapter_slug == adapter_slug)
            if operation:
                statement = statement.where(AdapterRunRecord.operation == operation)
            if status:
                statement = statement.where(AdapterRunRecord.status == status)
            return list(session.execute(statement.order_by(AdapterRunRecord.started_at)).scalars())

    def _mapping_payload(self, payload: dict[str, Any], *, tenant_id: str) -> dict[str, Any]:
        return {
            "tenant_id": tenant_id,
            "external_system": str(payload.get("external_system", "national_platform")),
            "direction": str(payload.get("direction", "outbound")),
            "local_aggregate_type": str(payload.get("local_aggregate_type", payload.get("aggregate_type", "unresolved"))),
            "local_aggregate_id": str(payload.get("local_aggregate_id", payload.get("aggregate_id", "")) or ""),
            "legacy_table": payload.get("legacy_table"),
            "legacy_id": payload.get("legacy_id"),
            "external_object_type": str(payload.get("external_object_type", payload.get("object_type", "unknown"))),
            "external_object_id": str(payload.get("external_object_id", payload.get("object_id", payload.get("idempotency_key", "pending")))),
            "protocol_version": payload.get("protocol_version"),
            "batch_no": payload.get("batch_no"),
            "status": str(payload.get("status", "pending")),
            "last_receipt_json": safe_json(payload.get("last_receipt_json") or payload.get("receipt_json") or {}),
            "extra_json": safe_json(payload.get("extra_json") or {}),
        }

    def _run_payload(self, payload: dict[str, Any], *, tenant_id: str) -> dict[str, Any]:
        status = str(payload.get("status", "succeeded"))
        target_count = int(payload.get("target_count", 1))
        failure_count = int(payload.get("failure_count", 0 if status in {"succeeded", "replayed"} else 1))
        success_count_value = payload.get("success_count")
        success_count = int(max(target_count - failure_count, 0) if success_count_value is None else success_count_value)
        finished_at = payload.get("finished_at")
        if isinstance(finished_at, str):
            finished_at = datetime.fromisoformat(finished_at)
        return {
            "tenant_id": tenant_id,
            "adapter_slug": str(payload["adapter_slug"]),
            "operation": str(payload["operation"]),
            "direction": str(payload.get("direction", "outbound")),
            "source_ref": payload.get("source_ref"),
            "idempotency_key": str(payload["idempotency_key"]),
            "status": status,
            "target_count": target_count,
            "success_count": success_count,
            "failure_count": failure_count,
            "receipt_json": safe_json(payload.get("receipt_json") or {}),
            "error_summary": payload.get("error_summary"),
            "started_at": payload.get("started_at") or _now(),
            "finished_at": finished_at or _now(),
        }
