from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from zw_brain.domain.models import (
    ActorOrgRoleBindingRecord,
    ActorProjectionRecord,
    DictProjectionRecord,
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
# Only legacy rows in these statuses may be claimed (rekeyed) by a first IAM login.
# `disabled` is deliberately excluded — a disabled legacy user must never lend its
# org-role bindings to an incoming IAM identity.
_CLAIMABLE_STATUSES = {"iam_account_missing", "unmatched"}
# Auxiliary identity match: IAF claim key → actor_projection.profile_json key.
_AUX_MATCH_KEYS = [("preferred_username", "account"), ("phone", "phone"), ("phone", "mobile"), ("email", "email")]


def _profile_without_unsafe_auth_fields(profile: dict[str, Any]) -> dict[str, Any]:
    safe_profile = safe_json(profile)
    for key in list(safe_profile.keys()):
        lowered = str(key).lower()
        if lowered in {"legacy_password", "password_hash", "password_salt", "old_token", "refresh_token", "verification_code", "sms_status", "session", "cookie", "client_secret"}:
            safe_profile.pop(key, None)
    return safe_profile


class ActorMatchError(ValueError):
    pass


class ActorDisabledError(ActorMatchError):
    """Raised when an IAF login resolves to a `disabled` actor row. A disabled identity must
    never be re-activated or handed a fresh active row at login (D62 A0 — disable enforced at
    the auth boundary). Surfaces map this to 403, like its ActorMatchError parent."""


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

    def upsert_dict(self, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> DictProjectionRecord:
        data = {
            "tenant_id": tenant_id,
            "dict_type": str(payload["dict_type"]),
            "code": str(payload["code"]),
            "name": str(payload.get("name", payload["code"])),
            "parent_code": payload.get("parent_code"),
            "seq": payload.get("seq"),
            "status": str(payload.get("status", "active")),
            "source_ref": payload.get("source_ref"),
            "profile_json": safe_json(payload.get("profile_json") or payload.get("profile") or {}),
        }
        return self._upsert(
            DictProjectionRecord,
            [DictProjectionRecord.tenant_id == tenant_id, DictProjectionRecord.dict_type == data["dict_type"], DictProjectionRecord.code == data["code"]],
            data,
        )

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
        # D62 A1: login / re-token (iaf:claims) NEVER derives bindings from token roles —
        # bindings are zw-brain's authoritative source, written only by legacy import +
        # in-product assign/revoke. Non-iaf upserts (legacy import) still seed bindings from
        # role_codes_json (that is how import populates the authoritative source).
        if str(data.get("source_ref") or "") == "iaf:claims":
            pass
        else:
            self._sync_actor_role_bindings(record)
        return record

    def claim_legacy_actor_by_iaf(
        self,
        *,
        iaf_sub: str,
        match_claims: dict[str, Any] | None = None,
        claims_profile: dict[str, Any] | None = None,
        token_role_codes: list[str] | None = None,
        display_name: str | None = None,
        org_code: str | None = None,
        legacy_actor_ref: str | None = None,
        source_ref: str | None = None,
        tenant_id: str = "sd-default",
    ) -> tuple[ActorProjectionRecord, str]:
        """Resolve an IAF `sub` to a single actor_projection row — claiming an existing
        legacy row in place rather than inserting a parallel one.

        Outcomes (second tuple element):
          - "updated_existing_sub": the sub already keyed a row; profile/roles refreshed.
          - "rekeyed_legacy": a claimable legacy row was rekeyed to the sub (id preserved),
            its bindings + legacy_object_mapping moved in the SAME transaction.
          - "inserted_fresh": no claimable legacy row; a new sub-keyed row was inserted.

        The whole rekey (actor row + bindings + mapping) happens in one session/commit so it
        is atomic — any failure rolls everything back (fail-closed). Login must NOT mutate
        bindings beyond this one-time move (wave-0 D-2 deferral); imported bindings stay SoT.
        """
        iaf_sub = str(iaf_sub or "")
        if not iaf_sub:
            raise ActorMatchError("iaf sub is required")
        match_claims = match_claims or {}
        claims_profile = claims_profile or {}
        token_role_codes = [str(role) for role in (token_role_codes or []) if str(role)]
        source_ref = source_ref or "iaf:claims"

        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            # 1. sub already owns a row → refresh in place, never touch bindings.
            current = session.execute(
                select(ActorProjectionRecord).where(
                    ActorProjectionRecord.tenant_id == tenant_id,
                    ActorProjectionRecord.external_actor_id == iaf_sub,
                )
            ).scalar_one_or_none()
            if current is not None:
                # D62 A0: a disabled identity must never be re-activated by re-login.
                # Before this guard `_apply_claim_to_actor` set status='active' on every
                # claim, silently resurrecting a disabled account on the next SSO login.
                if current.status == "disabled":
                    raise ActorDisabledError("actor_disabled")
                self._apply_claim_to_actor(
                    current,
                    iaf_sub=iaf_sub,
                    claims_profile=claims_profile,
                    token_role_codes=token_role_codes,
                    display_name=display_name,
                    org_code=org_code,
                    match_evidence={"method": "iaf_sub", "result": "existing_sub"},
                )
                session.commit()
                session.refresh(current)
                return current, "updated_existing_sub"

            # 2. resolve a legacy row to claim.
            legacy: ActorProjectionRecord | None = None
            method = "no_match"
            if legacy_actor_ref:
                legacy = session.execute(
                    select(ActorProjectionRecord).where(
                        ActorProjectionRecord.tenant_id == tenant_id,
                        ActorProjectionRecord.external_actor_id == str(legacy_actor_ref),
                    )
                ).scalar_one_or_none()
                method = "legacy_actor_ref"
            else:
                legacy, method = self._match_legacy_actor_in_session(session, match_claims, tenant_id=tenant_id)

            if legacy is not None and legacy.status in _CLAIMABLE_STATUSES:
                old_external = legacy.external_actor_id
                self._apply_claim_to_actor(
                    legacy,
                    iaf_sub=iaf_sub,
                    claims_profile=claims_profile,
                    token_role_codes=token_role_codes,
                    display_name=display_name,
                    org_code=org_code,
                    match_evidence={"method": method, "result": "rekeyed_legacy", "legacy_actor_ref": old_external},
                    preserve_legacy=True,
                )
                legacy.external_actor_id = iaf_sub
                self._rekey_bindings_in_session(session, tenant_id=tenant_id, old_external=old_external, new_external=iaf_sub)
                self._rekey_actor_object_mapping_in_session(session, tenant_id=tenant_id, old_ref=old_external, new_ref=iaf_sub)
                session.commit()
                session.refresh(legacy)
                return legacy, "rekeyed_legacy"

            # D62 A0: a disabled legacy row matched by sub/aux claims must fail closed — do
            # NOT mint a fresh active row for a deliberately disabled identity (that both
            # bypassed the disable and re-created the D51 duplicate it was meant to prevent).
            if legacy is not None and legacy.status == "disabled":
                raise ActorDisabledError("actor_disabled")

            # 3. no claimable legacy twin (none found, or only a non-disabled non-claimable
            #    row) → fresh sub-keyed row.
            record = self._insert_fresh_iaf_actor(
                session,
                iaf_sub=iaf_sub,
                claims_profile=claims_profile,
                token_role_codes=token_role_codes,
                display_name=display_name,
                org_code=org_code,
                source_ref=source_ref,
                tenant_id=tenant_id,
            )
            session.commit()
            session.refresh(record)
            return record, "inserted_fresh"

    def _match_legacy_actor_in_session(
        self, session: Session, claims: dict[str, Any], *, tenant_id: str
    ) -> tuple[ActorProjectionRecord | None, str]:
        matches: list[ActorProjectionRecord] = []
        for claim_key, profile_key in _AUX_MATCH_KEYS:
            value = claims.get(claim_key)
            if not value:
                continue
            matches.extend(self._find_actors_by_profile_value_in_session(session, profile_key, str(value), tenant_id=tenant_id))
        unique = {item.external_actor_id: item for item in matches}
        claimable = {key: rec for key, rec in unique.items() if rec.status in _CLAIMABLE_STATUSES}
        if len(claimable) > 1:
            raise ActorMatchError("iaf auxiliary claims matched multiple claimable actors")
        if len(claimable) == 1:
            return next(iter(claimable.values())), "auxiliary_claim"
        # No claimable match. A single non-claimable (e.g. disabled) match is returned so the
        # caller falls through to a fresh insert without inheriting that row's roles.
        if len(unique) == 1:
            return next(iter(unique.values())), "auxiliary_claim"
        return None, "no_match"

    def _apply_claim_to_actor(
        self,
        record: ActorProjectionRecord,
        *,
        iaf_sub: str,
        claims_profile: dict[str, Any],
        token_role_codes: list[str],
        display_name: str | None,
        org_code: str | None,
        match_evidence: dict[str, Any],
        preserve_legacy: bool = False,
    ) -> None:
        base = record.profile_json if isinstance(record.profile_json, dict) else {}
        merged = dict(base)
        for key, value in (claims_profile or {}).items():
            if value is not None:
                merged[key] = value
        merged["iaf_sub"] = iaf_sub
        merged["binding_status"] = "bound"
        merged["match_evidence"] = safe_json(match_evidence)
        if preserve_legacy and not merged.get("legacy_actor_ref"):
            merged["legacy_actor_ref"] = record.external_actor_id
        record.profile_json = _profile_without_unsafe_auth_fields(merged)
        record.status = "active"
        # D62 A1: login NEVER stamps token roles into role_codes_json — product roles are
        # zw-brain's authoritative actor_org_role_binding, not the generic shared IAM token.
        # The imported/assigned value is preserved untouched; token_role_codes is identity-only.
        if display_name:
            record.display_name = str(display_name)
        if org_code:
            record.org_code = org_code
        record.updated_at = _now()

    def _insert_fresh_iaf_actor(
        self,
        session: Session,
        *,
        iaf_sub: str,
        claims_profile: dict[str, Any],
        token_role_codes: list[str],
        display_name: str | None,
        org_code: str | None,
        source_ref: str,
        tenant_id: str,
    ) -> ActorProjectionRecord:
        profile = dict(claims_profile or {})
        profile["iaf_sub"] = iaf_sub
        profile["binding_status"] = "bound"
        record = ActorProjectionRecord(
            tenant_id=tenant_id,
            external_actor_id=iaf_sub,
            display_name=str(display_name or claims_profile.get("username") or iaf_sub),
            org_code=org_code,
            role_codes_json=safe_json(token_role_codes or []),
            status="active",
            source_ref=source_ref,
            profile_json=_profile_without_unsafe_auth_fields(profile),
        )
        session.add(record)
        session.flush()
        return record

    def _rekey_bindings_in_session(self, session: Session, *, tenant_id: str, old_external: str, new_external: str) -> int:
        if old_external == new_external:
            return 0
        existing_new = {
            (item.org_code, item.role_code): item
            for item in session.execute(
                select(ActorOrgRoleBindingRecord).where(
                    ActorOrgRoleBindingRecord.tenant_id == tenant_id,
                    ActorOrgRoleBindingRecord.external_actor_id == new_external,
                )
            ).scalars()
        }
        moved = 0
        for item in session.execute(
            select(ActorOrgRoleBindingRecord).where(
                ActorOrgRoleBindingRecord.tenant_id == tenant_id,
                ActorOrgRoleBindingRecord.external_actor_id == old_external,
            )
        ).scalars():
            if (item.org_code, item.role_code) in existing_new:
                # Target identity already owns this (org, role) → disable the stale duplicate
                # rather than violate uq_actor_org_role_binding_identity.
                item.binding_status = "disabled"
                item.updated_at = _now()
            else:
                item.external_actor_id = new_external
                item.updated_at = _now()
                moved += 1
        return moved

    def _rekey_actor_object_mapping_in_session(self, session: Session, *, tenant_id: str, old_ref: str, new_ref: str) -> int:
        if old_ref == new_ref:
            return 0
        updated = 0
        for item in session.execute(
            select(LegacyObjectMappingRecord).where(
                LegacyObjectMappingRecord.tenant_id == tenant_id,
                LegacyObjectMappingRecord.canonical_type == "ActorProjectionRecord",
                LegacyObjectMappingRecord.canonical_ref == old_ref,
            )
        ).scalars():
            item.canonical_ref = new_ref
            item.mapped_at = _now()
            updated += 1
        return updated

    def _find_actors_by_profile_value_in_session(
        self, session: Session, profile_key: str, value: str, *, tenant_id: str
    ) -> list[ActorProjectionRecord]:
        candidates = list(
            session.execute(
                select(ActorProjectionRecord).where(
                    ActorProjectionRecord.tenant_id == tenant_id,
                    ActorProjectionRecord.profile_json[profile_key].as_string() == value,
                )
            ).scalars()
        )
        if profile_key in _SENSITIVE_MATCH_KEYS:
            return [item for item in candidates if (item.profile_json or {}).get(profile_key) == value]
        return candidates

    def delete_actor_row(self, external_actor_id: str, *, tenant_id: str = "sd-default", source_ref_guard: str | None = "iaf:claims") -> bool:
        """Delete a single actor_projection row, guarded so the repair tool can only remove
        the thin login-created `iaf:claims` twins, never a legacy/imported row."""
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(
                select(ActorProjectionRecord).where(
                    ActorProjectionRecord.tenant_id == tenant_id,
                    ActorProjectionRecord.external_actor_id == external_actor_id,
                )
            ).scalar_one_or_none()
            if record is None:
                return False
            if source_ref_guard is not None and str(record.source_ref or "") != source_ref_guard:
                raise ActorMatchError(f"refuse to delete actor row source_ref={record.source_ref!r} (guard={source_ref_guard!r})")
            session.delete(record)
            session.commit()
            return True

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

    def get_org_by_code(self, org_code: str, *, tenant_id: str = "sd-default") -> OrgProjectionRecord | None:
        """索引点查（uq_org_projection_tenant_code）——派生带出用，避免拉全表 ~1.8 万行。"""
        items = self._list(
            select(OrgProjectionRecord).where(OrgProjectionRecord.tenant_id == tenant_id, OrgProjectionRecord.org_code == str(org_code))
        )
        return items[0] if items else None

    def list_orgs_by_name(self, org_name: str, *, tenant_id: str = "sd-default") -> list[OrgProjectionRecord]:
        """按机构名**精确**点查（大小写不敏感、去首尾空白）。返回 list 以暴露重名歧义——
        调用方（名/码归一）对多命中必须 fail-closed，不得擅自取第一条。"""
        name = str(org_name or "").strip()
        if not name:
            return []
        return self._list(
            select(OrgProjectionRecord).where(
                OrgProjectionRecord.tenant_id == tenant_id,
                func.lower(OrgProjectionRecord.org_name) == name.lower(),
            )
        )

    def get_actor_by_external_id(self, external_actor_id: str, *, tenant_id: str = "sd-default") -> ActorProjectionRecord | None:
        """身份带出用：按 external_actor_id 点查 actor 投影（含 org_code）。未命中返 None。"""
        if not external_actor_id:
            return None
        return self._get_actor(str(external_actor_id), tenant_id=tenant_id)

    def get_region_by_code(self, region_code: str, *, tenant_id: str = "sd-default") -> RegionProjectionRecord | None:
        items = self._list(
            select(RegionProjectionRecord).where(RegionProjectionRecord.tenant_id == tenant_id, RegionProjectionRecord.region_code == str(region_code))
        )
        return items[0] if items else None

    def list_region_children(self, parent_region_code: str, *, tenant_id: str = "sd-default") -> list[RegionProjectionRecord]:
        return self._list(
            select(RegionProjectionRecord)
            .where(RegionProjectionRecord.tenant_id == tenant_id, RegionProjectionRecord.parent_region_code == str(parent_region_code))
            .order_by(RegionProjectionRecord.region_code)
        )

    def list_org_children(self, parent_org_code: str, *, tenant_id: str = "sd-default") -> list[OrgProjectionRecord]:
        """某机构的直接下级机构（索引命中 parent_org_code）——部门可见域「本机构+下级」
        递归下钻用。当前 org_projection.parent_org_code 全空（legacy pub_organ_tree.PARENT_CODE
        尚未导入），故恒返 0 行、O(1)；父子树后续填充后下级自动生效，调用方零改动。"""
        code = str(parent_org_code or "")
        if not code:
            return []
        return self._list(
            select(OrgProjectionRecord)
            .where(OrgProjectionRecord.tenant_id == tenant_id, OrgProjectionRecord.parent_org_code == code)
            .order_by(OrgProjectionRecord.org_code)
        )

    def list_orgs_by_region(self, region_code: str, *, tenant_id: str = "sd-default", limit: int = 200) -> list[OrgProjectionRecord]:
        """选择器用：按区划在 DB 层过滤 + limit（避免 list_orgs 捞全 ~1.8 万行再内存切片）。

        region_code 为空 → 取该租户前 limit 个机构（前端再按需搜索）。
        """
        statement = select(OrgProjectionRecord).where(OrgProjectionRecord.tenant_id == tenant_id)
        if region_code:
            statement = statement.where(OrgProjectionRecord.region_code == str(region_code))
        return self._list(statement.order_by(OrgProjectionRecord.org_code).limit(limit))

    def search_orgs(
        self,
        *,
        tenant_id: str = "sd-default",
        keyword: str = "",
        region_code: str = "",
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[OrgProjectionRecord], int]:
        """机构选择器搜索分页：keyword 模糊匹 org_name/org_code（大小写不敏感），可叠加 region_code
        过滤；DB 层 offset/limit + count，返回 (当前页行, total)。避免捞全 ~1.8 万行再内存切片。"""
        base = select(OrgProjectionRecord).where(OrgProjectionRecord.tenant_id == tenant_id)
        if region_code:
            base = base.where(OrgProjectionRecord.region_code == str(region_code))
        kw = str(keyword or "").strip()
        if kw:
            like = f"%{kw}%"
            base = base.where(
                or_(
                    func.lower(OrgProjectionRecord.org_name).like(func.lower(like)),
                    func.lower(OrgProjectionRecord.org_code).like(func.lower(like)),
                )
            )
        total = self._count(base)
        rows = self._list(base.order_by(OrgProjectionRecord.org_code).offset(max(0, int(offset))).limit(int(limit)))
        return rows, total

    def list_dicts(self, dict_type: str, *, tenant_id: str = "sd-default", parent_code: str | None = None) -> list[DictProjectionRecord]:
        statement = select(DictProjectionRecord).where(
            DictProjectionRecord.tenant_id == tenant_id,
            DictProjectionRecord.dict_type == str(dict_type),
            DictProjectionRecord.status == "active",
        )
        if parent_code is not None:
            statement = statement.where(DictProjectionRecord.parent_code == str(parent_code))
        return self._list(statement.order_by(DictProjectionRecord.seq, DictProjectionRecord.code))

    def list_roles(self, *, tenant_id: str = "sd-default") -> list[RoleProjectionRecord]:
        return self._list(select(RoleProjectionRecord).where(RoleProjectionRecord.tenant_id == tenant_id).order_by(RoleProjectionRecord.role_code))

    def list_actors(self, *, tenant_id: str = "sd-default") -> list[ActorProjectionRecord]:
        return self._list(select(ActorProjectionRecord).where(ActorProjectionRecord.tenant_id == tenant_id).order_by(ActorProjectionRecord.external_actor_id))

    def list_actor_org_role_bindings(
        self,
        *,
        tenant_id: str = "sd-default",
        external_actor_id: str | None = None,
        binding_status: str | None = None,
        batch_no: str | None = None,
    ) -> list[ActorOrgRoleBindingRecord]:
        statement = select(ActorOrgRoleBindingRecord).where(ActorOrgRoleBindingRecord.tenant_id == tenant_id)
        if external_actor_id:
            statement = statement.where(ActorOrgRoleBindingRecord.external_actor_id == external_actor_id)
        if binding_status:
            statement = statement.where(ActorOrgRoleBindingRecord.binding_status == binding_status)
        if batch_no:
            statement = statement.where(ActorOrgRoleBindingRecord.batch_no == batch_no)
        return self._list(statement.order_by(ActorOrgRoleBindingRecord.external_actor_id, ActorOrgRoleBindingRecord.org_code, ActorOrgRoleBindingRecord.role_code))

    def list_active_actor_contexts(self, *, tenant_id: str = "sd-default", external_actor_id: str) -> list[dict[str, Any]]:
        contexts: list[dict[str, Any]] = []
        for item in self.list_actor_org_role_bindings(tenant_id=tenant_id, external_actor_id=external_actor_id, binding_status="active"):
            tags = item.tags_json if isinstance(item.tags_json, dict) else {}
            contexts.append(
                {
                    "org_code": item.org_code,
                    "role_code": item.role_code,
                    "actor_tags": tags,
                    "source_priority": item.source_priority,
                    "batch_no": item.batch_no,
                }
            )
        return contexts

    def disable_bindings_for_batch(self, batch_no: str, *, tenant_id: str = "sd-default") -> int:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            bindings = list(
                session.execute(
                    select(ActorOrgRoleBindingRecord).where(
                        ActorOrgRoleBindingRecord.tenant_id == tenant_id,
                        ActorOrgRoleBindingRecord.batch_no == batch_no,
                        ActorOrgRoleBindingRecord.binding_status == "active",
                    )
                ).scalars()
            )
            for item in bindings:
                item.binding_status = "disabled"
                item.updated_at = _now()
            session.commit()
            return len(bindings)

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
        """Thin wrapper kept for API symmetry — the single-row claim/rekey logic now lives in
        `claim_legacy_actor_by_iaf` so that login, re-import and the repair tool share one path."""
        iaf_sub = str(claims.get("sub") or "")
        if not iaf_sub:
            raise ActorMatchError("iaf sub is required")
        claims_profile = {
            "username": claims.get("preferred_username"),
            "email": claims.get("email"),
            "phone": claims.get("phone"),
        }
        record, _outcome = self.claim_legacy_actor_by_iaf(
            iaf_sub=iaf_sub,
            match_claims=claims,
            claims_profile={key: value for key, value in claims_profile.items() if value is not None},
            display_name=claims.get("preferred_username") or iaf_sub,
            tenant_id=tenant_id,
        )
        return record

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

    def list_policy_candidates(
        self,
        *,
        tenant_id: str = "sd-default",
        candidate_status: str | None = None,
        legacy_system: str | None = None,
        legacy_role_ref: str | None = None,
        capability_id: str | None = None,
        surface: str | None = None,
    ) -> list[LegacyPolicyMappingCandidateRecord]:
        statement = select(LegacyPolicyMappingCandidateRecord).where(LegacyPolicyMappingCandidateRecord.tenant_id == tenant_id)
        if candidate_status:
            statement = statement.where(LegacyPolicyMappingCandidateRecord.candidate_status == candidate_status)
        if legacy_system:
            statement = statement.where(LegacyPolicyMappingCandidateRecord.legacy_system == legacy_system)
        if legacy_role_ref:
            statement = statement.where(LegacyPolicyMappingCandidateRecord.legacy_role_ref == legacy_role_ref)
        if capability_id:
            statement = statement.where(LegacyPolicyMappingCandidateRecord.capability_id == capability_id)
        if surface:
            statement = statement.where(LegacyPolicyMappingCandidateRecord.surface == surface)
        return self._list(statement.order_by(LegacyPolicyMappingCandidateRecord.legacy_permission_ref, LegacyPolicyMappingCandidateRecord.capability_id))

    def review_policy_candidate(
        self,
        *,
        tenant_id: str,
        legacy_system: str,
        legacy_permission_ref: str,
        capability_id: str,
        candidate_status: str,
        review_evidence: dict[str, Any] | None = None,
    ) -> LegacyPolicyMappingCandidateRecord:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(
                select(LegacyPolicyMappingCandidateRecord).where(
                    LegacyPolicyMappingCandidateRecord.tenant_id == tenant_id,
                    LegacyPolicyMappingCandidateRecord.legacy_system == legacy_system,
                    LegacyPolicyMappingCandidateRecord.legacy_permission_ref == legacy_permission_ref,
                    LegacyPolicyMappingCandidateRecord.capability_id == capability_id,
                )
            ).scalar_one_or_none()
            if record is None:
                raise KeyError(f"{legacy_system}:{legacy_permission_ref}:{capability_id}")
            record.candidate_status = candidate_status
            if review_evidence:
                merged = dict(record.evidence_json) if isinstance(record.evidence_json, dict) else {}
                merged.update(review_evidence)
                record.evidence_json = safe_json(merged)
            record.updated_at = _now()
            session.commit()
            session.refresh(record)
            return record

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

    def sync_actor_bindings(
        self,
        actor: ActorProjectionRecord,
        bindings: list[dict[str, Any]] | None = None,
        *,
        batch_no: str | None = None,
    ) -> None:
        """Upsert explicit org-role bindings; disable stale rows for the same actor."""
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
            desired_specs: list[tuple[str, str, dict[str, Any]]] = []
            if bindings:
                for item in bindings:
                    org_code = str(item.get("org_code") or "")
                    role_code = str(item.get("role_code") or "")
                    if not org_code or not role_code:
                        continue
                    tags = item.get("tags_json") or item.get("actor_tags") or {}
                    desired_specs.append((org_code, role_code, safe_json(tags if isinstance(tags, dict) else {})))
            elif actor.org_code and actor.status == "active":
                for role in actor.role_codes_json or []:
                    if str(role):
                        desired_specs.append((actor.org_code, str(role), {}))
            desired_keys = {(org, role) for org, role, _ in desired_specs}
            spec_by_key = {(org, role): spec for org, role, spec in desired_specs}
            for item in existing:
                if (item.org_code, item.role_code) not in desired_keys:
                    item.binding_status = "disabled"
                    item.updated_at = _now()
            existing_keys = {(item.org_code, item.role_code): item for item in existing}
            for org_code, role_code, tags_json in desired_specs:
                evidence = safe_json({"source_ref": actor.source_ref, "binding_status": (actor.profile_json or {}).get("binding_status")})
                if (org_code, role_code) in existing_keys:
                    record = existing_keys[(org_code, role_code)]
                    record.binding_status = "active"
                    record.tags_json = tags_json
                    record.evidence_json = evidence
                    if batch_no:
                        record.batch_no = batch_no
                    record.updated_at = _now()
                else:
                    session.add(
                        ActorOrgRoleBindingRecord(
                            tenant_id=actor.tenant_id,
                            external_actor_id=actor.external_actor_id,
                            org_code=org_code,
                            role_code=role_code,
                            binding_status="active",
                            tags_json=tags_json,
                            batch_no=batch_no,
                            source_ref=actor.source_ref,
                            evidence_json=evidence,
                        )
                    )
            session.commit()

    def _sync_actor_role_bindings(self, actor: ActorProjectionRecord) -> None:
        self.sync_actor_bindings(actor)

    # ──────────────────────────────────────────────────────────────────────
    # In-product role governance writes (D62): single-edge assign/revoke +
    # actor lifecycle. zw-brain owns authorization — these are the only
    # admin-initiated writers to actor_org_role_binding / actor status.
    # ──────────────────────────────────────────────────────────────────────
    def get_actor(self, external_actor_id: str, *, tenant_id: str = "sd-default") -> ActorProjectionRecord | None:
        """Public accessor — handlers resolve an actor by external id."""
        return self._get_actor(external_actor_id, tenant_id=tenant_id)

    def assign_actor_role(
        self,
        *,
        external_actor_id: str,
        org_code: str,
        role_code: str,
        tenant_id: str = "sd-default",
        granted_by: str | None = None,
        note: str | None = None,
        tags_json: dict[str, Any] | None = None,
    ) -> ActorOrgRoleBindingRecord:
        """Grant (or re-activate) a single (actor, org, role) binding — idempotent on the
        unique key. This is zw-brain's authoritative role-assignment write."""
        external_actor_id = str(external_actor_id or "")
        org_code = str(org_code or "")
        role_code = str(role_code or "")
        if not external_actor_id or not org_code or not role_code:
            raise ActorMatchError("external_actor_id, org_code, role_code are required")
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(
                select(ActorOrgRoleBindingRecord).where(
                    ActorOrgRoleBindingRecord.tenant_id == tenant_id,
                    ActorOrgRoleBindingRecord.external_actor_id == external_actor_id,
                    ActorOrgRoleBindingRecord.org_code == org_code,
                    ActorOrgRoleBindingRecord.role_code == role_code,
                )
            ).scalar_one_or_none()
            evidence = safe_json({"action": "assign", "granted_by": granted_by, "note": note or None})
            if record is None:
                record = ActorOrgRoleBindingRecord(
                    tenant_id=tenant_id,
                    external_actor_id=external_actor_id,
                    org_code=org_code,
                    role_code=role_code,
                    binding_status="active",
                    tags_json=safe_json(tags_json if isinstance(tags_json, dict) else {}),
                    granted_by=granted_by,
                    source_ref="governance.actor.role.assign",
                    evidence_json=evidence,
                )
                session.add(record)
                session.flush()
            else:
                record.binding_status = "active"
                record.granted_by = granted_by
                if tags_json is not None:
                    record.tags_json = safe_json(tags_json if isinstance(tags_json, dict) else {})
                record.source_ref = "governance.actor.role.assign"
                record.evidence_json = evidence
                record.updated_at = _now()
            record_id = record.id
            self._refresh_actor_role_codes_in_session(session, tenant_id=tenant_id, external_actor_id=external_actor_id)
            session.commit()
            return session.execute(select(ActorOrgRoleBindingRecord).where(ActorOrgRoleBindingRecord.id == record_id)).scalar_one()

    def revoke_actor_role(
        self,
        *,
        external_actor_id: str,
        org_code: str,
        role_code: str,
        tenant_id: str = "sd-default",
    ) -> bool:
        """Disable a single (actor, org, role) binding. Returns True if an active binding
        was found and disabled, False otherwise (idempotent)."""
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(
                select(ActorOrgRoleBindingRecord).where(
                    ActorOrgRoleBindingRecord.tenant_id == tenant_id,
                    ActorOrgRoleBindingRecord.external_actor_id == str(external_actor_id or ""),
                    ActorOrgRoleBindingRecord.org_code == str(org_code or ""),
                    ActorOrgRoleBindingRecord.role_code == str(role_code or ""),
                )
            ).scalar_one_or_none()
            if record is None or record.binding_status != "active":
                return False
            record.binding_status = "disabled"
            record.updated_at = _now()
            self._refresh_actor_role_codes_in_session(session, tenant_id=tenant_id, external_actor_id=str(external_actor_id or ""))
            session.commit()
            return True

    def set_actor_status(
        self,
        *,
        external_actor_id: str,
        status: str,
        tenant_id: str = "sd-default",
    ) -> ActorProjectionRecord | None:
        """Set actor lifecycle status (active/disabled). Bindings are left intact so that
        re-enabling restores prior access; the auth gates fail closed on `disabled`."""
        status = str(status or "")
        if status not in {"active", "disabled"}:
            raise ActorMatchError(f"unsupported actor status: {status!r}")
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(
                select(ActorProjectionRecord).where(
                    ActorProjectionRecord.tenant_id == tenant_id,
                    ActorProjectionRecord.external_actor_id == str(external_actor_id or ""),
                )
            ).scalar_one_or_none()
            if record is None:
                return None
            record.status = status
            record.updated_at = _now()
            record_id = record.id
            session.commit()
            return session.execute(select(ActorProjectionRecord).where(ActorProjectionRecord.id == record_id)).scalar_one()

    def _refresh_actor_role_codes_in_session(self, session: Session, *, tenant_id: str, external_actor_id: str) -> None:
        """Keep actor_projection.role_codes_json mirrored to the actor's ACTIVE bindings so the
        (now vestigial) snapshot fallback never disagrees with the authoritative binding source
        (D62 A1c). Roles are read from bindings everywhere that matters; this just stops a stale
        role_codes_json from resurrecting a revoked role via the browser no-binding fallback."""
        # R-002: callers mutate binding_status (revoke→disabled / re-activate→active) but the
        # session is autoflush=False, so the ACTIVE-binding SELECT below would read STALE
        # pre-mutation rows (revoke would re-add the role, re-activate would miss it). Flush
        # the pending mutation first so the mirror reflects the post-mutation truth.
        session.flush()
        active = session.execute(
            select(ActorOrgRoleBindingRecord).where(
                ActorOrgRoleBindingRecord.tenant_id == tenant_id,
                ActorOrgRoleBindingRecord.external_actor_id == external_actor_id,
                ActorOrgRoleBindingRecord.binding_status == "active",
            )
        ).scalars()
        role_codes = sorted({item.role_code for item in active})
        actor = session.execute(
            select(ActorProjectionRecord).where(
                ActorProjectionRecord.tenant_id == tenant_id,
                ActorProjectionRecord.external_actor_id == external_actor_id,
            )
        ).scalar_one_or_none()
        if actor is not None:
            actor.role_codes_json = safe_json(role_codes)
            actor.updated_at = _now()

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

    def _count(self, statement: Any) -> int:
        """统计某 select 的命中总数（分页 total 用）；以子查询包裹，方言无关。"""
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return int(session.execute(select(func.count()).select_from(statement.subquery())).scalar() or 0)
