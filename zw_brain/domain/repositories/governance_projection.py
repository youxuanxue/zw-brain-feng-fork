from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from zw_brain.domain.models import (
    ActorProjectionRecord,
    LegacyObjectMappingRecord,
    LegacyPolicyMappingCandidateRecord,
    OrgProjectionRecord,
    RegionProjectionRecord,
    RoleProjectionRecord,
    TenantProjectionRecord,
)
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.sanitization import legacy_mapping_payload, safe_json


def _now() -> datetime:
    return datetime.now(UTC)


class GovernanceProjectionRepository:
    def upsert_tenant(self, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> TenantProjectionRecord:
        data = {
            "tenant_id": str(payload.get("tenant_id", tenant_id)),
            "tenant_name": str(payload.get("tenant_name", payload.get("name", payload.get("tenant_id", tenant_id)))),
            "status": str(payload.get("status", "active")),
            "source_ref": payload.get("source_ref"),
            "profile_json": safe_json(payload.get("profile_json") or payload.get("profile") or {}),
        }
        return self._upsert(TenantProjectionRecord, [TenantProjectionRecord.tenant_id == data["tenant_id"]], data)

    def upsert_org(self, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> OrgProjectionRecord:
        data = {
            "tenant_id": tenant_id,
            "org_code": str(payload["org_code"]),
            "org_name": str(payload.get("org_name", payload["org_code"])),
            "parent_org_code": payload.get("parent_org_code"),
            "region_code": payload.get("region_code"),
            "status": str(payload.get("status", "active")),
            "source_ref": payload.get("source_ref"),
            "profile_json": safe_json(payload.get("profile_json") or payload.get("profile") or {}),
        }
        return self._upsert(OrgProjectionRecord, [OrgProjectionRecord.tenant_id == tenant_id, OrgProjectionRecord.org_code == data["org_code"]], data)

    def upsert_region(self, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> RegionProjectionRecord:
        data = {
            "tenant_id": tenant_id,
            "region_code": str(payload["region_code"]),
            "region_name": str(payload.get("region_name", payload["region_code"])),
            "parent_region_code": payload.get("parent_region_code"),
            "region_level": payload.get("region_level"),
            "status": str(payload.get("status", "active")),
            "source_ref": payload.get("source_ref"),
            "profile_json": safe_json(payload.get("profile_json") or payload.get("profile") or {}),
        }
        return self._upsert(RegionProjectionRecord, [RegionProjectionRecord.tenant_id == tenant_id, RegionProjectionRecord.region_code == data["region_code"]], data)

    def upsert_role(self, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> RoleProjectionRecord:
        data = {
            "tenant_id": tenant_id,
            "role_code": str(payload["role_code"]),
            "role_name": str(payload.get("role_name", payload["role_code"])),
            "status": str(payload.get("status", "active")),
            "source_ref": payload.get("source_ref"),
            "profile_json": safe_json(payload.get("profile_json") or payload.get("profile") or {}),
        }
        return self._upsert(RoleProjectionRecord, [RoleProjectionRecord.tenant_id == tenant_id, RoleProjectionRecord.role_code == data["role_code"]], data)

    def upsert_actor(self, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> ActorProjectionRecord:
        data = {
            "tenant_id": tenant_id,
            "external_actor_id": str(payload["external_actor_id"]),
            "display_name": str(payload.get("display_name", payload["external_actor_id"])),
            "org_code": payload.get("org_code"),
            "role_codes_json": safe_json(payload.get("role_codes") or payload.get("role_codes_json") or []),
            "status": str(payload.get("status", "active")),
            "source_ref": payload.get("source_ref"),
            "profile_json": safe_json(payload.get("profile_json") or payload.get("profile") or {}),
        }
        return self._upsert(ActorProjectionRecord, [ActorProjectionRecord.tenant_id == tenant_id, ActorProjectionRecord.external_actor_id == data["external_actor_id"]], data)

    def import_legacy_policy_candidate(self, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> LegacyPolicyMappingCandidateRecord:
        data = {
            "tenant_id": tenant_id,
            "legacy_system": str(payload.get("legacy_system", "dsp-bsp")),
            "legacy_permission_ref": str(payload["legacy_permission_ref"]),
            "legacy_role_ref": payload.get("legacy_role_ref"),
            "capability_id": str(payload["capability_id"]),
            "surface": payload.get("surface"),
            "candidate_status": str(payload.get("candidate_status", "pending_review")),
            "evidence_json": safe_json(payload.get("evidence_json") or {}),
        }
        return self._upsert(
            LegacyPolicyMappingCandidateRecord,
            [
                LegacyPolicyMappingCandidateRecord.tenant_id == tenant_id,
                LegacyPolicyMappingCandidateRecord.legacy_system == data["legacy_system"],
                LegacyPolicyMappingCandidateRecord.legacy_permission_ref == data["legacy_permission_ref"],
                LegacyPolicyMappingCandidateRecord.capability_id == data["capability_id"],
            ],
            data,
        )

    def list_tenants(self) -> list[TenantProjectionRecord]:
        return self._list(select(TenantProjectionRecord).order_by(TenantProjectionRecord.tenant_id))

    def list_orgs(self, *, tenant_id: str = "sd-default") -> list[OrgProjectionRecord]:
        return self._list(select(OrgProjectionRecord).where(OrgProjectionRecord.tenant_id == tenant_id).order_by(OrgProjectionRecord.org_code))

    def list_regions(self, *, tenant_id: str = "sd-default") -> list[RegionProjectionRecord]:
        return self._list(select(RegionProjectionRecord).where(RegionProjectionRecord.tenant_id == tenant_id).order_by(RegionProjectionRecord.region_code))

    def list_roles(self, *, tenant_id: str = "sd-default") -> list[RoleProjectionRecord]:
        return self._list(select(RoleProjectionRecord).where(RoleProjectionRecord.tenant_id == tenant_id).order_by(RoleProjectionRecord.role_code))

    def list_actors(self, *, tenant_id: str = "sd-default") -> list[ActorProjectionRecord]:
        return self._list(select(ActorProjectionRecord).where(ActorProjectionRecord.tenant_id == tenant_id).order_by(ActorProjectionRecord.external_actor_id))

    def list_policy_candidates(self, *, tenant_id: str = "sd-default", candidate_status: str | None = None) -> list[LegacyPolicyMappingCandidateRecord]:
        statement = select(LegacyPolicyMappingCandidateRecord).where(LegacyPolicyMappingCandidateRecord.tenant_id == tenant_id)
        if candidate_status:
            statement = statement.where(LegacyPolicyMappingCandidateRecord.candidate_status == candidate_status)
        return self._list(statement.order_by(LegacyPolicyMappingCandidateRecord.legacy_permission_ref))

    def upsert_legacy_object_mapping(self, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> LegacyObjectMappingRecord | None:
        if not payload.get("source_ref"):
            return None
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = self._upsert_legacy_object_mapping_in_session(session, payload, tenant_id=tenant_id)
            session.commit()
            return record

    def _upsert_legacy_object_mapping_in_session(self, session: Session, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> LegacyObjectMappingRecord:
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
            record = LegacyObjectMappingRecord(**mapping)
            session.add(record)
            session.flush()
            for item in existing_for_legacy:
                item.mapping_status = "conflicted"
                item.mapped_at = _now()
            return record
        record.source_ref = mapping["source_ref"]
        record.mapping_status = "conflicted" if len(existing_for_legacy) > 1 else mapping["mapping_status"]
        record.evidence_json = safe_json(mapping.get("evidence_json"))
        record.mapped_at = _now()
        session.flush()
        return record

    def _upsert(self, model: Any, where: list[Any], data: dict[str, Any]) -> Any:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(select(model).where(*where)).scalar_one_or_none()
            if record is None:
                record = model(**data)
                session.add(record)
                session.flush()
            else:
                for key, value in data.items():
                    setattr(record, key, value)
                record.updated_at = _now()
            session.commit()
            return session.execute(select(model).where(model.id == record.id)).scalar_one()

    def _list(self, statement: Any) -> list[Any]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(session.execute(statement).scalars())
