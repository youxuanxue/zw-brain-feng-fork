from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from zw_brain.domain.models import GatewayRuntimeStatusProjectionRecord
from zw_brain.domain.repositories.legacy_mapping import upsert_legacy_mapping_in_session
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.sanitization import summary_with_source_kind


def _now() -> datetime:
    return _utc_naive(datetime.now(UTC))


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


class GatewayRuntimeRepository:
    def has_statuses(self, *, tenant_id: str = "sd-default") -> bool:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return session.execute(
                select(GatewayRuntimeStatusProjectionRecord.id)
                .where(GatewayRuntimeStatusProjectionRecord.tenant_id == tenant_id)
                .limit(1)
            ).scalar_one_or_none() is not None

    def list_statuses(self, *, tenant_id: str = "sd-default") -> list[GatewayRuntimeStatusProjectionRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(
                session.execute(
                    select(GatewayRuntimeStatusProjectionRecord)
                    .where(GatewayRuntimeStatusProjectionRecord.tenant_id == tenant_id)
                    .order_by(GatewayRuntimeStatusProjectionRecord.gateway_instance_id)
                ).scalars()
            )

    def upsert_heartbeat(self, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> GatewayRuntimeStatusProjectionRecord:
        SessionLocal = create_session_factory()
        instance_id = str(payload["gateway_instance_id"])
        reported_at = payload.get("last_reported_at")
        if isinstance(reported_at, str):
            reported_at = datetime.fromisoformat(reported_at.replace("Z", "+00:00"))
        if reported_at is None:
            reported_at = _now()
        else:
            reported_at = _utc_naive(reported_at)
        now = _now()
        summary_json = summary_with_source_kind(payload.get("summary_json"), payload.get("source_ref"))
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
                    runtime_profile=payload.get("runtime_profile"),
                    status=str(payload.get("status", "online")),
                    last_reported_at=reported_at,
                    source_ref=payload.get("source_ref"),
                    summary_json=summary_json,
                    generated_at=now,
                )
                session.add(record)
            else:
                record.gateway_address_ref = payload.get("gateway_address_ref", record.gateway_address_ref)
                if payload.get("runtime_profile") is not None:
                    record.runtime_profile = payload["runtime_profile"]
                record.status = str(payload.get("status", record.status))
                record.last_reported_at = reported_at
                record.source_ref = payload.get("source_ref", record.source_ref)
                record.summary_json = summary_json or record.summary_json
                record.generated_at = now
            upsert_legacy_mapping_in_session(
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
