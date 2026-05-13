from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from zw_brain.domain.models import LegacyObjectMappingRecord
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.sanitization import legacy_mapping_payload, safe_json


def _now() -> datetime:
    return datetime.now(UTC)


def upsert_legacy_mapping_in_session(session: Any, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> None:
    if not payload.get("source_ref"):
        return
    mapping = legacy_mapping_payload(payload, tenant_id=tenant_id)
    existing_for_legacy = list(
        session.execute(
            select(LegacyObjectMappingRecord).where(
                LegacyObjectMappingRecord.tenant_id == tenant_id,
                LegacyObjectMappingRecord.legacy_system == mapping["legacy_system"],
                LegacyObjectMappingRecord.legacy_object_type == mapping["legacy_object_type"],
                LegacyObjectMappingRecord.legacy_object_ref == mapping["legacy_object_ref"],
            )
        ).scalars()
    )
    record = next(
        (
            item
            for item in existing_for_legacy
            if item.canonical_type == mapping["canonical_type"] and item.canonical_ref == mapping["canonical_ref"]
        ),
        None,
    )
    if record is None:
        mapping["mapping_status"] = "conflicted" if existing_for_legacy else mapping["mapping_status"]
        session.add(LegacyObjectMappingRecord(**mapping))
        for item in existing_for_legacy:
            item.mapping_status = "conflicted"
            item.mapped_at = _now()
    else:
        record.source_ref = mapping["source_ref"]
        record.mapping_status = "conflicted" if len(existing_for_legacy) > 1 else mapping["mapping_status"]
        record.evidence_json = safe_json(mapping.get("evidence_json"))
        record.mapped_at = _now()


class LegacyObjectMappingRepository:
    def list_mappings(
        self,
        *,
        tenant_id: str = "sd-default",
        canonical_type: str | None = None,
        canonical_ref: str | None = None,
    ) -> list[LegacyObjectMappingRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            statement = select(LegacyObjectMappingRecord).where(LegacyObjectMappingRecord.tenant_id == tenant_id)
            if canonical_type:
                statement = statement.where(LegacyObjectMappingRecord.canonical_type == canonical_type)
            if canonical_ref:
                statement = statement.where(LegacyObjectMappingRecord.canonical_ref == canonical_ref)
            return list(session.execute(statement.order_by(LegacyObjectMappingRecord.mapped_at)).scalars())

    def resolve_canonical_ref(
        self,
        *,
        legacy_system: str,
        legacy_object_type: str,
        legacy_object_ref: str,
        canonical_type: str,
        tenant_id: str = "sd-default",
    ) -> str | None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            records = list(
                session.execute(
                    select(LegacyObjectMappingRecord).where(
                        LegacyObjectMappingRecord.tenant_id == tenant_id,
                        LegacyObjectMappingRecord.legacy_system == legacy_system,
                        LegacyObjectMappingRecord.legacy_object_type == legacy_object_type,
                        LegacyObjectMappingRecord.legacy_object_ref == legacy_object_ref,
                        LegacyObjectMappingRecord.canonical_type == canonical_type,
                    )
                ).scalars()
            )
        refs = {record.canonical_ref for record in records if record.mapping_status == "mapped"} or {
            record.canonical_ref for record in records
        }
        return next(iter(refs)) if len(refs) == 1 else None

    def upsert_mapping(
        self,
        payload: dict[str, Any],
        *,
        tenant_id: str = "sd-default",
    ) -> LegacyObjectMappingRecord | None:
        if not payload.get("source_ref"):
            return None
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            upsert_legacy_mapping_in_session(session, payload, tenant_id=tenant_id)
            session.commit()
            mapping = legacy_mapping_payload(payload, tenant_id=tenant_id)
            return session.execute(
                select(LegacyObjectMappingRecord).where(
                    LegacyObjectMappingRecord.tenant_id == tenant_id,
                    LegacyObjectMappingRecord.legacy_system == mapping["legacy_system"],
                    LegacyObjectMappingRecord.legacy_object_type == mapping["legacy_object_type"],
                    LegacyObjectMappingRecord.legacy_object_ref == mapping["legacy_object_ref"],
                    LegacyObjectMappingRecord.canonical_type == mapping["canonical_type"],
                    LegacyObjectMappingRecord.canonical_ref == mapping["canonical_ref"],
                )
            ).scalar_one_or_none()
