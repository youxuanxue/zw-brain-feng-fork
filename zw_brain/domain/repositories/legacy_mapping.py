from __future__ import annotations

from typing import Any

from sqlalchemy import select

from zw_brain.domain.models import LegacyObjectMappingRecord
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.sanitization import legacy_mapping_payload, safe_json


class LegacyObjectMappingRepository:
    def list_mappings(
        self,
        *,
        tenant_id: str = "default",
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

    def upsert_mapping(
        self,
        payload: dict[str, Any],
        *,
        tenant_id: str = "default",
    ) -> LegacyObjectMappingRecord:
        SessionLocal = create_session_factory()
        mapping = legacy_mapping_payload(payload, tenant_id=tenant_id)
        with SessionLocal() as session:
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
                record = LegacyObjectMappingRecord(**mapping)
                session.add(record)
            else:
                record.source_ref = mapping["source_ref"]
                record.evidence_json = safe_json(mapping.get("evidence_json"))
            session.commit()
            session.refresh(record)
            return record
