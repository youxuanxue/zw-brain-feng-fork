from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from zw_brain.domain.models import GatewayRuntimeStatusProjectionRecord, LegacyObjectMappingRecord
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.sanitization import adapter_source_kind, legacy_mapping_payload, safe_json


def _now() -> datetime:
    return datetime.now(UTC)


class GatewayRuntimeRepository:
    def has_statuses(self, *, tenant_id: str = "default") -> bool:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return session.execute(
                select(GatewayRuntimeStatusProjectionRecord.id)
                .where(GatewayRuntimeStatusProjectionRecord.tenant_id == tenant_id)
                .limit(1)
            ).scalar_one_or_none() is not None

    def list_statuses(self, *, tenant_id: str = "default") -> list[GatewayRuntimeStatusProjectionRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(
                session.execute(
                    select(GatewayRuntimeStatusProjectionRecord)
                    .where(GatewayRuntimeStatusProjectionRecord.tenant_id == tenant_id)
                    .order_by(GatewayRuntimeStatusProjectionRecord.gateway_instance_id)
                ).scalars()
            )

    def upsert_heartbeat(self, payload: dict[str, Any], *, tenant_id: str = "default") -> GatewayRuntimeStatusProjectionRecord:
        SessionLocal = create_session_factory()
        instance_id = str(payload["gateway_instance_id"])
        reported_at = payload.get("last_reported_at")
        if isinstance(reported_at, str):
            reported_at = datetime.fromisoformat(reported_at.replace("Z", "+00:00"))
        if reported_at is None:
            reported_at = _now()
        now = _now()
        summary_json = safe_json(payload.get("summary_json") or {}) | {"source_kind": adapter_source_kind(payload.get("source_ref"))}
        with SessionLocal() as session:
            record = session.execute(
                select(GatewayRuntimeStatusProjectionRecord).where(
                    GatewayRuntimeStatusProjectionRecord.tenant_id == tenant_id,
                    GatewayRuntimeStatusProjectionRecord.gateway_instance_id == instance_id,
                )
            ).scalar_one_or_none()
            if record is None:
                record = GatewayRuntimeStatusProjectionRecord(
                    tenant_id=tenant_id,
                    gateway_instance_id=instance_id,
                    gateway_address_ref=payload.get("gateway_address_ref"),
                    status=str(payload.get("status", "online")),
                    last_reported_at=reported_at,
                    source_ref=payload.get("source_ref"),
                    summary_json=summary_json,
                    generated_at=now,
                )
                session.add(record)
            else:
                record.gateway_address_ref = payload.get("gateway_address_ref", record.gateway_address_ref)
                record.status = str(payload.get("status", record.status))
                record.last_reported_at = reported_at
                record.source_ref = payload.get("source_ref", record.source_ref)
                record.summary_json = summary_json or record.summary_json
                record.generated_at = now
            self._upsert_legacy_mapping(
                session,
                {
                    "source_ref": record.source_ref,
                    "legacy_object_ref": payload.get("legacy_object_ref") or instance_id,
                    "canonical_type": "gateway_runtime_status_projection",
                    "canonical_ref": instance_id,
                    "evidence_json": {"status": record.status},
                },
                tenant_id=tenant_id,
            )
            session.commit()
            session.refresh(record)
            return record

    def _upsert_legacy_mapping(self, session: Any, payload: dict[str, Any], *, tenant_id: str) -> None:
        if not payload.get("source_ref"):
            return
        mapping = legacy_mapping_payload(payload, tenant_id=tenant_id)
        record = session.execute(
            select(LegacyObjectMappingRecord).where(
                LegacyObjectMappingRecord.tenant_id == tenant_id,
                LegacyObjectMappingRecord.legacy_system == mapping["legacy_system"],
                LegacyObjectMappingRecord.legacy_object_type == mapping["legacy_object_type"],
                LegacyObjectMappingRecord.legacy_object_ref == mapping["legacy_object_ref"],
                LegacyObjectMappingRecord.canonical_type == mapping["canonical_type"],
                LegacyObjectMappingRecord.canonical_ref == mapping["canonical_ref"],
            )
        ).scalar_one_or_none()
        if record is None:
            session.add(LegacyObjectMappingRecord(**mapping))
        else:
            record.source_ref = mapping["source_ref"]
            record.evidence_json = mapping["evidence_json"]
