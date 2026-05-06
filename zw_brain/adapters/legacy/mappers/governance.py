"""Governance mapper: dsp_bsp.pub_organ / pub_region / pub_user / pub_role → projections.

Step 1 of the 8-step bridging chain. Every downstream mapper references org_code,
region_code, actor display, or role_code — so this must run first or those references
fall back to bare legacy IDs.

Real-secret fields (password / token / key / hmac / OTP / ukey / IP whitelist / longblob
seal) are dropped at the row boundary; business-visible sensitive fields (姓名/手机号/
邮箱/身份证/地址) flow through and are masked at the read layer per [2026-05-06] policy.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from zw_brain.adapters.legacy._common import ImportStats, finish_run, schema_from_dump_name
from zw_brain.adapters.legacy.parser import MysqldumpParser
from zw_brain.adapters.legacy.tenant_normalizer import DEFAULT_TENANT, legacy_system_for
from zw_brain.domain.repositories.external_adapter import ExternalAdapterRepository
from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
from zw_brain.domain.repositories.legacy_mapping import LegacyObjectMappingRepository

# Real secrets — not allowed under [2026-05-06] sensitive policy override.
PUB_USER_DROP_FIELDS = {
    "PASSWORD",
    "OTP_KEY",
    "SENSITIVE_HMAC",
    "UKEY",
    "IP_LIST",
    "IP_ACCESS_STATUS",
    "ELEC_IMG",
    "PWD_LASTUPDATE",
    "PWD_CHANGED",
}
PUB_ROLE_DROP_FIELDS = {"HMAC"}


class GovernanceMapper:
    HANDLED_TABLES = {"pub_organ", "pub_region", "pub_user", "pub_role"}
    ADAPTER_SLUG = "legacy.bsp.governance"

    def __init__(self, *, tenant_id: str = DEFAULT_TENANT):
        self.tenant_id = tenant_id
        self.governance_repo = GovernanceProjectionRepository()
        self.legacy_repo = LegacyObjectMappingRepository()
        self.adapter_repo = ExternalAdapterRepository()

    def import_dump(self, dump_path: Path) -> ImportStats:
        schema = schema_from_dump_name(dump_path.name)
        legacy_system = legacy_system_for(schema)
        stats = ImportStats(schema=schema, dump_path=dump_path)
        started_at = datetime.now(UTC)

        for table, row in MysqldumpParser(dump_path).iter_rows():
            if table not in self.HANDLED_TABLES:
                stats.skip(table)
                continue
            handler = getattr(self, f"_map_{table[len('pub_'):]}")
            try:
                handler(row, stats, legacy_system)
            except KeyError as exc:
                stats.bump(table, "errors")
                stats.skipped.setdefault(f"{table}.missing_field:{exc.args[0]}", 0)
                stats.skipped[f"{table}.missing_field:{exc.args[0]}"] += 1

        finish_run(self.adapter_repo, stats, adapter_slug=self.ADAPTER_SLUG, dump_path=dump_path, started_at=started_at, tenant_id=self.tenant_id)
        return stats

    # ------------------------------------------------------------------
    # per-table handlers
    # ------------------------------------------------------------------

    def _map_organ(self, row: dict[str, Any], stats: ImportStats, legacy_system: str) -> None:
        code = row["CODE"]
        self.governance_repo.upsert_org(
            {
                "org_code": code,
                "org_name": row.get("NAME") or code,
                "parent_org_code": _parent_from_trace(row.get("TRACE_CODE"), code),
                "region_code": row.get("REGION_CODE"),
                "status": _status_flag(row.get("STATUS")),
                "source_ref": f"{legacy_system}:pub_organ:{code}",
                "profile_json": {
                    "short_name": row.get("SHORT_NAME"),
                    "region_name": row.get("REGION_NAME"),
                    "organ_type": row.get("ORGAN_TYPE"),
                    "organ_level": row.get("ORGAN_LEVEL"),
                    "society_code": row.get("SOCIETY_CODE"),
                    "org_num": row.get("ORG_NUM"),
                },
            },
            tenant_id=self.tenant_id,
        )
        self._write_legacy_mapping(
            legacy_system=legacy_system,
            legacy_object_type="pub_organ",
            legacy_object_ref=code,
            canonical_type="OrgProjectionRecord",
            canonical_ref=code,
            evidence={"name": row.get("NAME"), "region_code": row.get("REGION_CODE")},
        )
        stats.bump("pub_organ")

    def _map_region(self, row: dict[str, Any], stats: ImportStats, legacy_system: str) -> None:
        code = row["CODE"]
        self.governance_repo.upsert_region(
            {
                "region_code": code,
                "region_name": row.get("NAME") or code,
                "parent_region_code": row.get("PARENT_CODE"),
                "region_level": row.get("GRADE"),
                "status": _status_flag(row.get("STATUS")),
                "source_ref": f"{legacy_system}:pub_region:{code}",
                "profile_json": {
                    "short_code": row.get("SHORT_CODE"),
                    "tree_code": row.get("TREE_CODE"),
                },
            },
            tenant_id=self.tenant_id,
        )
        self._write_legacy_mapping(
            legacy_system=legacy_system,
            legacy_object_type="pub_region",
            legacy_object_ref=code,
            canonical_type="RegionProjectionRecord",
            canonical_ref=code,
            evidence={"name": row.get("NAME"), "grade": row.get("GRADE")},
        )
        stats.bump("pub_region")

    def _map_user(self, row: dict[str, Any], stats: ImportStats, legacy_system: str) -> None:
        external_id = row["ID"]
        scrubbed = {k: v for k, v in row.items() if k not in PUB_USER_DROP_FIELDS}
        role_codes = _split_role_codes(scrubbed.get("ROLE_VALUE") or scrubbed.get("ROLE_CODE"))
        self.governance_repo.upsert_actor(
            {
                "external_actor_id": external_id,
                "display_name": scrubbed.get("NAME") or scrubbed.get("ACCOUNT") or external_id,
                "org_code": scrubbed.get("ORG_CODE"),
                "role_codes": role_codes,
                "status": _status_flag(scrubbed.get("STATUS")),
                "source_ref": f"{legacy_system}:pub_user:{external_id}",
                "profile_json": {
                    "account": scrubbed.get("ACCOUNT"),
                    # business-visible sensitive — read layer must mask
                    "phone": scrubbed.get("PHONE"),
                    "mobile": scrubbed.get("MOBILE"),
                    "email": scrubbed.get("EMAIL"),
                    "identity_num": scrubbed.get("IDENTITY_NUM"),
                    "address": scrubbed.get("ADDRESS"),
                    "region_code": scrubbed.get("REGION_CODE"),
                    "region_name": scrubbed.get("REGION_NAME"),
                    "org_name": scrubbed.get("ORG_NAME"),
                    "user_type": scrubbed.get("USER_TYPE"),
                    "is_admin": scrubbed.get("IS_ADMIN"),
                },
            },
            tenant_id=self.tenant_id,
        )
        self._write_legacy_mapping(
            legacy_system=legacy_system,
            legacy_object_type="pub_user",
            legacy_object_ref=external_id,
            canonical_type="ActorProjectionRecord",
            canonical_ref=external_id,
            evidence={"account": scrubbed.get("ACCOUNT"), "org_code": scrubbed.get("ORG_CODE")},
        )
        stats.bump("pub_user")

    def _map_role(self, row: dict[str, Any], stats: ImportStats, legacy_system: str) -> None:
        scrubbed = {k: v for k, v in row.items() if k not in PUB_ROLE_DROP_FIELDS}
        # `VALUE` is the unique business code (per UNIQUE KEY PUB_ROLE_VALUE_UK); fall back to ID.
        code = scrubbed.get("VALUE") or scrubbed["ID"]
        self.governance_repo.upsert_role(
            {
                "role_code": code,
                "role_name": scrubbed.get("NAME") or code,
                "status": _status_flag(scrubbed.get("STATUS")),
                "source_ref": f"{legacy_system}:pub_role:{code}",
                "profile_json": {
                    "internal_id": scrubbed.get("ID"),
                    "type": scrubbed.get("TYPE"),
                    "weight": scrubbed.get("WEIGHT"),
                    "parent_id": scrubbed.get("PARENT_ID"),
                    "app_code": scrubbed.get("APP_CODE"),
                },
            },
            tenant_id=self.tenant_id,
        )
        self._write_legacy_mapping(
            legacy_system=legacy_system,
            legacy_object_type="pub_role",
            legacy_object_ref=code,
            canonical_type="RoleProjectionRecord",
            canonical_ref=code,
            evidence={"name": scrubbed.get("NAME"), "internal_id": scrubbed.get("ID")},
        )
        stats.bump("pub_role")

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _write_legacy_mapping(
        self,
        *,
        legacy_system: str,
        legacy_object_type: str,
        legacy_object_ref: str,
        canonical_type: str,
        canonical_ref: str,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        self.legacy_repo.upsert_mapping(
            {
                "source_ref": f"{legacy_system}:{legacy_object_type}:{legacy_object_ref}",
                "legacy_system": legacy_system,
                "legacy_object_type": legacy_object_type,
                "legacy_object_ref": legacy_object_ref,
                "canonical_type": canonical_type,
                "canonical_ref": canonical_ref,
                "evidence_json": evidence or {},
            },
            tenant_id=self.tenant_id,
        )


def _status_flag(raw: Any) -> str:
    if raw in ("1", 1, True, "active"):
        return "active"
    if raw in ("0", 0, False, "inactive", "disabled"):
        return "inactive"
    return "unknown"


def _parent_from_trace(trace_code: Any, self_code: Any) -> str | None:
    if not trace_code or not isinstance(trace_code, str):
        return None
    parts = [p for p in trace_code.split("-") if p]
    if len(parts) < 2:
        return None
    if parts[-1] == str(self_code):
        return parts[-2]
    return None


def _split_role_codes(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw if item]
    return [piece.strip() for piece in str(raw).split(",") if piece.strip()]
