from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from zw_brain.domain.models import GatewayRuntimeStatusProjectionRecord
from zw_brain.shared.db import create_session_factory


def _now() -> datetime:
    return datetime.now(UTC)


class GatewayRuntimeRepository:
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
                    summary_json=payload.get("summary_json") or {},
                    generated_at=now,
                )
                session.add(record)
            else:
                record.gateway_address_ref = payload.get("gateway_address_ref", record.gateway_address_ref)
                record.status = str(payload.get("status", record.status))
                record.last_reported_at = reported_at
                record.source_ref = payload.get("source_ref", record.source_ref)
                record.summary_json = payload.get("summary_json") or record.summary_json
                record.generated_at = now
            session.commit()
            session.refresh(record)
            return record
