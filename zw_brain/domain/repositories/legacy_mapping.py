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
    """Upsert one legacy → canonical mapping。

    Conflict 定义（修正后）：**同一旧对象映射到同一 canonical_type 但不同
    canonical_ref**——这才是"不知道这个旧对象代表哪一条新记录"的真冲突。
    跨 canonical_type 是合法分裂（如 data_apply → application_record +
    DeliveryTaskRecord 同时存在，一条申请派生一条交付任务），不算冲突。

    判定算法：
        1. 查同 (legacy_system, legacy_object_type, legacy_object_ref,
                canonical_type) 范围内的现有 mapping
        2. 若该范围内已有但 canonical_ref 不同 → 都标 conflicted
        3. 若该范围内已有同 canonical_ref → 幂等更新，保持 mapped
        4. 若该范围内没有现有 → 新增并标 mapped
    """
    if not payload.get("source_ref"):
        return
    mapping = legacy_mapping_payload(payload, tenant_id=tenant_id)
    existing_same_canonical_type = list(
        session.execute(
            select(LegacyObjectMappingRecord).where(
                LegacyObjectMappingRecord.tenant_id == tenant_id,
                LegacyObjectMappingRecord.legacy_system == mapping["legacy_system"],
                LegacyObjectMappingRecord.legacy_object_type == mapping["legacy_object_type"],
                LegacyObjectMappingRecord.legacy_object_ref == mapping["legacy_object_ref"],
                LegacyObjectMappingRecord.canonical_type == mapping["canonical_type"],
            )
        ).scalars()
    )
    record = next(
        (item for item in existing_same_canonical_type if item.canonical_ref == mapping["canonical_ref"]),
        None,
    )
    if record is None:
        # 同 canonical_type 范围内首次插入；若该范围已有别的 canonical_ref，标 conflicted
        mapping["mapping_status"] = "conflicted" if existing_same_canonical_type else mapping["mapping_status"]
        session.add(LegacyObjectMappingRecord(**mapping))
        for item in existing_same_canonical_type:
            item.mapping_status = "conflicted"
            item.mapped_at = _now()
    else:
        record.source_ref = mapping["source_ref"]
        # 同 canonical_type 范围内多于一条 = 仍是冲突
        record.mapping_status = "conflicted" if len(existing_same_canonical_type) > 1 else mapping["mapping_status"]
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
