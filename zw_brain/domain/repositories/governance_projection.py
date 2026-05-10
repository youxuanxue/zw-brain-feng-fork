from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from zw_brain.domain.models import (
    ActorOrgRoleBindingRecord,
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


_FAIL_CLOSED_STATUSES = {"disabled", "unmatched", "iam_account_missing"}
_SENSITIVE_MATCH_KEYS = {"phone", "mobile", "email"}


def _profile_without_unsafe_auth_fields(profile: dict[str, Any]) -> dict[str, Any]:
    safe_profile = safe_json(profile)
    for key in list(safe_profile.keys()):
        lowered = str(key).lower()
        if lowered in {"legacy_password", "password_hash", "password_salt", "old_token", "refresh_token", "verification_code", "sms_status", "session", "cookie", "client_secret"}:
            safe_profile.pop(key, None)
    return safe_profile


class ActorMatchError(ValueError):
    pass


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
        profile = _profile_without_unsafe_auth_fields(payload.get("profile_json") or payload.get("profile") or {})
        external_actor_id = str(payload.get("external_actor_id") or "")
        iaf_sub = str(payload.get("iaf_sub") or profile.get("iaf_sub") or "")
        if not iaf_sub and str(payload.get("source_ref") or "") == "iaf:claims":
            iaf_sub = external_actor_id
        if not iaf_sub:
            legacy_ref = str(payload.get("legacy_actor_ref") or payload.get("legacy_user_id") or external_actor_id or payload.get("source_ref") or "legacy_actor_missing_iaf")
            profile = profile | {
                "binding_status": payload.get("binding_status") or "iam_account_missing",
                "binding_reason": payload.get("binding_reason") or "iaf_sub_required",
                "legacy_actor_ref": legacy_ref,
            }
            external_actor_id = legacy_ref
            status = str(payload.get("status") or "iam_account_missing")
        else:
            external_actor_id = iaf_sub
            status = str(payload.get("status", "active"))
            profile = profile | {"iaf_sub": iaf_sub, "binding_status": payload.get("binding_status") or "bound"}
        data = {
            "tenant_id": tenant_id,
            "external_actor_id": external_actor_id,
            "display_name": str(payload.get("display_name", external_actor_id)),
            "org_code": payload.get("org_code"),
            "role_codes_json": safe_json(payload.get("role_codes") or payload.get("role_codes_json") or []),
            "status": status,
            "source_ref": payload.get("source_ref"),
            "profile_json": profile,
        }
        record = self._upsert(ActorProjectionRecord, [ActorProjectionRecord.tenant_id == tenant_id, ActorProjectionRecord.external_actor_id == data["external_actor_id"]], data)
        self._sync_actor_role_bindings(record)
        return record

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

    def list_actor_org_role_bindings(self, *, tenant_id: str = "sd-default", external_actor_id: str | None = None) -> list[ActorOrgRoleBindingRecord]:
        statement = select(ActorOrgRoleBindingRecord).where(ActorOrgRoleBindingRecord.tenant_id == tenant_id)
        if external_actor_id:
            statement = statement.where(ActorOrgRoleBindingRecord.external_actor_id == external_actor_id)
        return self._list(statement.order_by(ActorOrgRoleBindingRecord.external_actor_id, ActorOrgRoleBindingRecord.org_code, ActorOrgRoleBindingRecord.role_code))

    def find_actor_for_iaf_claims(self, claims: dict[str, Any], *, tenant_id: str = "sd-default") -> ActorProjectionRecord | None:
        iaf_sub = str(claims.get("sub") or "")
        if iaf_sub:
            actor = self._get_actor(iaf_sub, tenant_id=tenant_id)
            if actor is not None:
                return actor
        matches: list[ActorProjectionRecord] = []
        for claim_key, profile_key in [("preferred_username", "account"), ("phone", "phone"), ("phone", "mobile"), ("email", "email")]:
            value = claims.get(claim_key)
            if not value:
                continue
            matches.extend(self._find_actors_by_profile_value(profile_key, str(value), tenant_id=tenant_id))
        unique = {item.external_actor_id: item for item in matches}
        if len(unique) == 1:
            return next(iter(unique.values()))
        if len(unique) > 1:
            raise ActorMatchError("iaf auxiliary claims matched multiple actors")
        return None

    def bind_actor_to_iaf_claims(self, claims: dict[str, Any], *, tenant_id: str = "sd-default") -> ActorProjectionRecord:
        iaf_sub = str(claims.get("sub") or "")
        if not iaf_sub:
            raise ActorMatchError("iaf sub is required")
        actor = self.find_actor_for_iaf_claims(claims, tenant_id=tenant_id)
        if actor is None:
            return self.upsert_actor(
                {
                    "iaf_sub": iaf_sub,
                    "display_name": claims.get("preferred_username") or iaf_sub,
                    "status": "iam_account_missing",
                    "source_ref": "iaf:claims",
                    "profile_json": {
                        "iaf_sub": iaf_sub,
                        "username": claims.get("preferred_username"),
                        "binding_status": "iam_account_missing",
                        "match_evidence": {"method": "iaf_sub", "result": "no_local_projection"},
                    },
                },
                tenant_id=tenant_id,
            )
        if actor.external_actor_id == iaf_sub:
            return actor
        profile = dict(actor.profile_json or {})
        evidence = {
            "method": "auxiliary_claim",
            "preferred_username_matched": bool(claims.get("preferred_username") and claims.get("preferred_username") == profile.get("account")),
            "phone_matched": bool(claims.get("phone") and claims.get("phone") in {profile.get("phone"), profile.get("mobile")}),
            "email_matched": bool(claims.get("email") and claims.get("email") == profile.get("email")),
        }
        return self.upsert_actor(
            {
                "iaf_sub": iaf_sub,
                "display_name": actor.display_name,
                "org_code": actor.org_code,
                "role_codes": actor.role_codes_json,
                "status": "active",
                "source_ref": actor.source_ref,
                "profile_json": profile | {"legacy_actor_ref": actor.external_actor_id, "match_evidence": evidence},
            },
            tenant_id=tenant_id,
        )

    def mark_legacy_actor_unmatched(self, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> ActorProjectionRecord:
        legacy_ref = str(payload.get("legacy_actor_ref") or payload.get("external_actor_id") or payload.get("legacy_user_id") or "")
        if not legacy_ref:
            raise ActorMatchError("legacy actor ref is required")
        profile = _profile_without_unsafe_auth_fields(payload.get("profile_json") or payload.get("profile") or {})
        return self.upsert_actor(
            {
                "external_actor_id": legacy_ref,
                "display_name": payload.get("display_name") or legacy_ref,
                "org_code": payload.get("org_code"),
                "role_codes": [],
                "status": payload.get("status") or "unmatched",
                "source_ref": payload.get("source_ref"),
                "profile_json": profile | {"binding_status": payload.get("status") or "unmatched", "legacy_actor_ref": legacy_ref, "match_evidence": safe_json(payload.get("match_evidence") or {})},
            },
            tenant_id=tenant_id,
        )

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

    def _sync_actor_role_bindings(self, actor: ActorProjectionRecord) -> None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            existing = list(
                session.execute(
                    select(ActorOrgRoleBindingRecord).where(
                        ActorOrgRoleBindingRecord.tenant_id == actor.tenant_id,
                        ActorOrgRoleBindingRecord.external_actor_id == actor.external_actor_id,
                    )
                ).scalars()
            )
            desired = set()
            if actor.org_code and actor.status == "active":
                desired = {(actor.org_code, str(role)) for role in actor.role_codes_json or [] if str(role)}
            for item in existing:
                if (item.org_code, item.role_code) not in desired:
                    item.binding_status = "disabled"
                    item.updated_at = _now()
            existing_keys = {(item.org_code, item.role_code): item for item in existing}
            for org_code, role_code in desired:
                if (org_code, role_code) in existing_keys:
                    record = existing_keys[(org_code, role_code)]
                    record.binding_status = "active"
                    record.evidence_json = safe_json({"source_ref": actor.source_ref, "binding_status": actor.profile_json.get("binding_status")})
                    record.updated_at = _now()
                else:
                    session.add(
                        ActorOrgRoleBindingRecord(
                            tenant_id=actor.tenant_id,
                            external_actor_id=actor.external_actor_id,
                            org_code=org_code,
                            role_code=role_code,
                            binding_status="active",
                            source_ref=actor.source_ref,
                            evidence_json=safe_json({"source_ref": actor.source_ref, "binding_status": actor.profile_json.get("binding_status")}),
                        )
                    )
            session.commit()

    def _get_actor(self, external_actor_id: str, *, tenant_id: str = "sd-default") -> ActorProjectionRecord | None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return session.execute(select(ActorProjectionRecord).where(ActorProjectionRecord.tenant_id == tenant_id, ActorProjectionRecord.external_actor_id == external_actor_id)).scalar_one_or_none()

    def _find_actors_by_profile_value(self, profile_key: str, value: str, *, tenant_id: str = "sd-default") -> list[ActorProjectionRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            candidates = list(
                session.execute(
                    select(ActorProjectionRecord).where(
                        ActorProjectionRecord.tenant_id == tenant_id,
                        ActorProjectionRecord.profile_json[profile_key].as_string() == value,
                    )
                ).scalars()
            )
            if profile_key in _SENSITIVE_MATCH_KEYS:
                return [item for item in candidates if item.profile_json.get(profile_key) == value]
            return candidates

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
