"""Governance mapper: BSP governance tables → zw-brain projections."""
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
from zw_brain.domain.role_codes import BUSINESS_ROLE_CODES, LEGACY_ROLE_CODES, SYSTEM_ROLE_CODES, TAG_LEAD_DEPT
from zw_brain.shared.sanitization import safe_json

_PRODUCT_ROLE_ALLOWLIST = frozenset(BUSINESS_ROLE_CODES)
_FORBIDDEN_IMPORT_ROLE_CODES = frozenset(SYSTEM_ROLE_CODES)

# `iaf-sd-<sha1>` 是 build_m0_sd_default_fixtures.py 生成的占位 sub（基线 §1.4：
# iaf_sub 必须来自 IAF directory，占位 sub 进 canonical 会污染 actor_projection 且
# 无法过 OIDC 验签）。mapper 解析 binding 后立即归一化为空，由下游 fail-closed
# 路径统一处理为 iam_account_missing —— 不再依赖手工跑 ingest_iam_sub_backfill 拦截。
_IAF_SUB_PLACEHOLDER_PREFIX = "iaf-sd-"


def _normalize_iaf_sub(raw: str) -> str:
    """Strip + 占位前缀检测；占位视同未注入返回空字符串。"""
    sub = (raw or "").strip()
    if not sub or sub.startswith(_IAF_SUB_PLACEHOLDER_PREFIX):
        return ""
    return sub

REAL_SECRET_FIELDS = {
    "password",
    "pwd",
    "passwd",
    "password_hash",
    "password_salt",
    "token",
    "access_token",
    "refresh_token",
    "verification_code",
    "sms_status",
    "session",
    "session_id",
    "cookie",
    "client_secret",
    "secret",
    "otp_key",
    "sensitive_hmac",
    "ukey",
    "ip_list",
    "ip_access_status",
    "elec_img",
    "pwd_lastupdate",
    "pwd_changed",
    "hmac",
}
PUB_USER_DROP_FIELDS = {item.upper() for item in REAL_SECRET_FIELDS}
PUB_ROLE_DROP_FIELDS = {"HMAC"}


class GovernanceMapper:
    HANDLED_TABLES = {
        "pub_organ",
        "pub_region",
        "pub_user",
        "pub_role",
        "pub_user_role",
        "pub_user_organ",
        "pub_user_organ_role",
        "pub_resource",
        "pub_function",
        "pub_role_function",
        "pub_role_resource",
        "pub_apps",
        "sys_department",
        "sys_region",
        "sys_user",
        "sys_role",
        "sys_user_role",
        "sys_role_permission",
        "sys_user_department",
        "sys_permission",
        "iaf_binding_manifest",
        "role_mapping_manifest",
        "capability_mapping_manifest",
    }
    _PUB_IDENTITY_TABLES = frozenset({"pub_user", "pub_user_role", "pub_user_organ", "pub_user_organ_role"})
    # 必须经 manifest（role_mapping_manifest / capability_mapping_manifest）批量映射才能进投影/候选；
    # 没有 manifest 时 fail-closed，不允许走 per-row no-op 默默丢数据。
    _PUB_GOVERNANCE_TABLES = frozenset(
        {
            "pub_user_role",
            "pub_user_organ",
            "pub_user_organ_role",
            "pub_resource",
            "pub_function",
            "pub_role_function",
            "pub_role_resource",
        }
    )
    ADAPTER_SLUG = "legacy.bsp.governance"

    def __init__(self, *, tenant_id: str = DEFAULT_TENANT):
        self.tenant_id = tenant_id
        self.governance_repo = GovernanceProjectionRepository()
        self.legacy_repo = LegacyObjectMappingRepository()
        self.adapter_repo = ExternalAdapterRepository()

    def import_dump(self, dump_path: Path, *, dry_run: bool = False) -> ImportStats:
        schema = schema_from_dump_name(dump_path.name)
        legacy_system = legacy_system_for(schema)
        stats = ImportStats(schema=schema, dump_path=dump_path, mode="dry-run" if dry_run else "apply")
        started_at = datetime.now(UTC)
        rows_by_table: dict[str, list[dict[str, Any]]] = {}

        for table, row in MysqldumpParser(dump_path).iter_rows():
            table_name = table.lower()
            if table_name not in self.HANDLED_TABLES:
                stats.skip(table)
                continue
            stats.bump_source(table_name)
            rows_by_table.setdefault(table_name, []).append(row)

        defer_pub_identity = bool(
            rows_by_table.get("pub_user_organ_role")
            or rows_by_table.get("iaf_binding_manifest")
            or rows_by_table.get("role_mapping_manifest")
        )
        batch_no = stats.dump_path.stem

        for table_name, rows in rows_by_table.items():
            if table_name.startswith("pub_"):
                # 治理身份 / 权限关系表必须经 manifest 批量路径处理；缺 manifest 时 fail-closed。
                if table_name in self._PUB_GOVERNANCE_TABLES:
                    if defer_pub_identity:
                        # 由 _map_pub_governance / _import_pub_role_permission_candidates 统一消化
                        continue
                    # business-level fail-closed (warn): rows are intentionally dropped because
                    # the manifest isn't in this batch. Filed in stats.issues so error_summary
                    # records it; doesn't count toward failure_count or bump status to
                    # partial_failure. Customer dumps without manifest land here on 7980/52241
                    # governance rows — strict 模式不该卡在这里。
                    stats.add_issue(
                        "missing_manifest",
                        table_name,
                        "",
                        {"reason": "pub_governance_relation_requires_manifest", "row_count": len(rows)},
                        severity="warn",
                    )
                    continue
                if defer_pub_identity and table_name in self._PUB_IDENTITY_TABLES:
                    # pub_user 留给 _map_pub_governance 统一消化（line 312 起按 user_id
                    # 重新分组）。parse 阶段 line 110 已 bump_source 一次，这里不再叠加
                    # （R-301 修死代码：旧实现在此对 rows 再 bump_source 一遍，会让
                    # source_counts["pub_user"] 翻倍，纯统计漂移）。
                    continue
                handler = getattr(self, f"_map_{table_name[len('pub_'):]}")
                for row in rows:
                    try:
                        handler(row, stats, legacy_system, dry_run=dry_run)
                    except KeyError as exc:
                        stats.bump(table_name, "errors")
                        stats.skipped.setdefault(f"{table_name}.missing_field:{exc.args[0]}", 0)
                        stats.skipped[f"{table_name}.missing_field:{exc.args[0]}"] += 1

        if defer_pub_identity and rows_by_table.get("pub_user"):
            self._map_pub_governance(rows_by_table, stats, legacy_system, dry_run=dry_run, batch_no=batch_no)

        if any(table_name.startswith("sys_") or table_name.endswith("_manifest") for table_name in rows_by_table):
            self._map_sys_governance(rows_by_table, stats, legacy_system, dry_run=dry_run)
        stats.issues.sort(key=lambda item: (str(item.get("type")), str(item.get("table")), str(item.get("legacy_ref"))))

        if not dry_run:
            finish_run(self.adapter_repo, stats, adapter_slug=self.ADAPTER_SLUG, dump_path=dump_path, started_at=started_at, tenant_id=self.tenant_id)
        return stats

    def _map_organ(self, row: dict[str, Any], stats: ImportStats, legacy_system: str, *, dry_run: bool = False) -> None:
        code = str(row["CODE"])
        payload = {
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
        }
        self._write_projection("org_projection", dry_run, lambda: self.governance_repo.upsert_org(payload, tenant_id=self.tenant_id), stats)
        self._write_legacy_mapping(
            legacy_system=legacy_system,
            legacy_object_type="pub_organ",
            legacy_object_ref=code,
            canonical_type="OrgProjectionRecord",
            canonical_ref=code,
            evidence={"name": row.get("NAME"), "region_code": row.get("REGION_CODE")},
            dry_run=dry_run,
            stats=stats,
        )
        stats.bump("pub_organ")

    def _map_region(self, row: dict[str, Any], stats: ImportStats, legacy_system: str, *, dry_run: bool = False) -> None:
        code = str(row["CODE"])
        payload = {
            "region_code": code,
            "region_name": row.get("NAME") or code,
            "parent_region_code": row.get("PARENT_CODE"),
            "region_level": row.get("GRADE"),
            "status": _status_flag(row.get("STATUS")),
            "source_ref": f"{legacy_system}:pub_region:{code}",
            "profile_json": {"short_code": row.get("SHORT_CODE"), "tree_code": row.get("TREE_CODE")},
        }
        self._write_projection("region_projection", dry_run, lambda: self.governance_repo.upsert_region(payload, tenant_id=self.tenant_id), stats)
        self._write_legacy_mapping(
            legacy_system=legacy_system,
            legacy_object_type="pub_region",
            legacy_object_ref=code,
            canonical_type="RegionProjectionRecord",
            canonical_ref=code,
            evidence={"name": row.get("NAME"), "grade": row.get("GRADE")},
            dry_run=dry_run,
            stats=stats,
        )
        stats.bump("pub_region")

    def _map_user(self, row: dict[str, Any], stats: ImportStats, legacy_system: str, *, dry_run: bool = False) -> None:
        external_id = str(row["ID"])
        scrubbed = _scrub_row(row, PUB_USER_DROP_FIELDS)
        role_codes = _split_role_codes(scrubbed.get("ROLE_VALUE") or scrubbed.get("ROLE_CODE"))
        payload = {
            "external_actor_id": external_id,
            "display_name": scrubbed.get("NAME") or scrubbed.get("ACCOUNT") or external_id,
            "org_code": scrubbed.get("ORG_CODE"),
            "role_codes": role_codes,
            "status": _status_flag(scrubbed.get("STATUS")),
            "source_ref": f"{legacy_system}:pub_user:{external_id}",
            "profile_json": _scrub_profile(
                {
                    "account": scrubbed.get("ACCOUNT"),
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
                }
            ),
        }
        self._write_projection("actor_projection", dry_run, lambda: self.governance_repo.upsert_actor(payload, tenant_id=self.tenant_id), stats)
        self._write_legacy_mapping(
            legacy_system=legacy_system,
            legacy_object_type="pub_user",
            legacy_object_ref=external_id,
            canonical_type="ActorProjectionRecord",
            canonical_ref=external_id,
            evidence={"account": scrubbed.get("ACCOUNT"), "org_code": scrubbed.get("ORG_CODE")},
            dry_run=dry_run,
            stats=stats,
        )
        stats.bump("pub_user")

    def _map_role(self, row: dict[str, Any], stats: ImportStats, legacy_system: str, *, dry_run: bool = False) -> None:
        scrubbed = _scrub_row(row, PUB_ROLE_DROP_FIELDS)
        code = str(scrubbed.get("VALUE") or scrubbed["ID"])
        payload = {
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
        }
        self._write_projection("role_projection", dry_run, lambda: self.governance_repo.upsert_role(payload, tenant_id=self.tenant_id), stats)
        self._write_legacy_mapping(
            legacy_system=legacy_system,
            legacy_object_type="pub_role",
            legacy_object_ref=code,
            canonical_type="RoleProjectionRecord",
            canonical_ref=code,
            evidence={"name": scrubbed.get("NAME"), "internal_id": scrubbed.get("ID")},
            dry_run=dry_run,
            stats=stats,
        )
        stats.bump("pub_role")

    def _map_apps(self, row: dict[str, Any], stats: ImportStats, legacy_system: str, *, dry_run: bool = False) -> None:
        secret = _row_value(row, "SECRET")
        if secret not in (None, ""):
            # warn: sanitization heads-up; the pub_apps row IS still bumped below.
            stats.add_issue(
                "sensitive_field_blocked",
                "pub_apps",
                _string_value(row, "CODE", "ID"),
                {"field": "SECRET"},
                severity="warn",
            )
        stats.bump("pub_apps")

    def _map_pub_governance(
        self,
        rows_by_table: dict[str, list[dict[str, Any]]],
        stats: ImportStats,
        legacy_system: str,
        *,
        dry_run: bool,
        batch_no: str,
    ) -> None:
        tenant_payload = {
            "tenant_id": self.tenant_id,
            "tenant_name": "山东省默认租户" if self.tenant_id == DEFAULT_TENANT else self.tenant_id,
            "status": "active",
            "source_ref": f"{legacy_system}:tenant:{self.tenant_id}",
            "profile_json": {"import_source": "bsp_pub_governance", "batch_no": batch_no},
        }
        self._write_projection("tenant_projection", dry_run, lambda: self.governance_repo.upsert_tenant(tenant_payload, tenant_id=self.tenant_id), stats)

        # 显式 fail-closed 标记：defer_pub_identity 路径下缺 iaf_binding_manifest / role_mapping_manifest
        # 等同于"M0 baseline 不到位"，必须在 receipt 顶层 issue 流标记一条；否则只能靠下游 per-row
        # unmapped_role / iam_account_missing 摘要才能反推 root cause，对 M0 实施工程师不友好。
        manifest_tables_present = {
            "iaf_binding_manifest": bool(rows_by_table.get("iaf_binding_manifest")),
            "role_mapping_manifest": bool(rows_by_table.get("role_mapping_manifest")),
            "capability_mapping_manifest": bool(rows_by_table.get("capability_mapping_manifest")),
        }
        for manifest_table, present in manifest_tables_present.items():
            if not present:
                # warn-level: the manifest's absence is by-design fail-closed; downstream
                # per-row issues will surface as iam_account_missing / unmapped_role etc.
                # Recording this at the top of the receipt makes the root cause auditable
                # without bumping the run to partial_failure.
                stats.add_issue(
                    "missing_manifest",
                    manifest_table,
                    "",
                    {"reason": "m0_baseline_manifest_absent", "pub_governance_will_fail_closed": True},
                    severity="warn",
                )

        binding_index = _binding_index(rows_by_table.get("iaf_binding_manifest", []))
        role_mapping = _role_mapping_index(rows_by_table.get("role_mapping_manifest", []), stats)
        capability_index = _capability_mapping_index(rows_by_table.get("capability_mapping_manifest", []), stats)

        users_by_code: dict[str, dict[str, Any]] = {}
        users_by_id: dict[str, dict[str, Any]] = {}
        for row in rows_by_table.get("pub_user", []):
            user_id = str(row["ID"])
            user_code = _string_value(row, "USER_CODE", "ID") or user_id
            users_by_id[user_id] = row
            users_by_code[user_code] = row
            stats.bump("pub_user")

        organ_roles = rows_by_table.get("pub_user_organ_role", [])
        user_org_roles: dict[str, list[dict[str, Any]]] = {}
        for row in organ_roles:
            user_code = _string_value(row, "USER_CODE")
            if user_code:
                user_org_roles.setdefault(user_code, []).append(row)
            stats.bump("pub_user_organ_role")

        for _row in rows_by_table.get("pub_user_role", []):
            stats.bump("pub_user_role")
        for _row in rows_by_table.get("pub_user_organ", []):
            stats.bump("pub_user_organ")

        for user_id, row in users_by_id.items():
            user_code = _string_value(row, "USER_CODE", "ID") or user_id
            account = _string_value(row, "ACCOUNT")
            binding = binding_index.get(f"id:{user_id}") or binding_index.get(f"code:{user_code}") or binding_index.get(f"account:{account}")
            iaf_sub = _normalize_iaf_sub(_string_value(binding or {}, "IAF_SUB", "SUB", "IAM_SUB", "USER_SUB"))
            status = _status_flag(row.get("STATUS"))
            binding_specs: list[dict[str, Any]] = []
            binding_by_key: dict[tuple[str, str], dict[str, Any]] = {}
            if iaf_sub and status == "active":
                for rel in user_org_roles.get(user_code, []):
                    org_code = _string_value(rel, "ORG_CODE")
                    raw_role_code = _string_value(rel, "ROLE_CODE", "ROLE_VALUE")
                    if not org_code or not raw_role_code:
                        continue
                    # BSP schema (`pub_user_organ_role.ROLE_CODE`): "角色编码,以'#'号分隔"
                    # Real sd-default 数据出现 'ROLE_DATA_LEADER#ROLE_MGMT_LEADER' 等多角色串；
                    # 必须先拆才能逐项 normalize，否则整串当成单一未知 ref 全部丢成 missing_role_mapping。
                    for legacy_role in _split_pub_organ_role_codes(raw_role_code):
                        normalized = _normalize_legacy_role(legacy_role, role_mapping, stats, table="pub_user_organ_role", legacy_ref=f"{user_code}:{org_code}:{legacy_role}")
                        if normalized is None:
                            continue
                        key = (org_code, normalized["role_code"])
                        tags_json = normalized.get("tags_json") or {}
                        if key in binding_by_key:
                            binding_by_key[key]["tags_json"] = {**binding_by_key[key].get("tags_json", {}), **tags_json}
                        else:
                            binding_by_key[key] = {
                                "org_code": org_code,
                                "role_code": normalized["role_code"],
                                "tags_json": tags_json,
                                "source_priority": "pub_user_organ_role",
                            }
                binding_specs = list(binding_by_key.values())
                if not binding_specs:
                    fallback_roles = _normalize_role_list(_split_role_codes(row.get("ROLE_VALUE") or row.get("ROLE_CODE")), role_mapping, stats, table="pub_user", legacy_ref=user_id)
                    org_code = _string_value(row, "ORG_CODE")
                    if org_code:
                        for role_code, tags_json in fallback_roles:
                            binding_specs.append(
                                {
                                    "org_code": org_code,
                                    "role_code": role_code,
                                    "tags_json": tags_json,
                                    "source_priority": "pub_user.ROLE_VALUE",
                                }
                            )

            issue_status = None
            role_codes: list[str] = []
            main_org = _string_value(row, "ORG_CODE")
            if not iaf_sub:
                issue_status = "iam_account_missing"
                status = "iam_account_missing"
                # warn: actor is upserted with status='iam_account_missing' sentinel; row is not lost,
                # just tagged. Bumping failure_count for these is per-row business marker noise.
                stats.add_issue(
                    "iam_account_missing",
                    "pub_user",
                    user_id,
                    {"account": account, "user_code": user_code},
                    severity="warn",
                )
                for legacy_role in _split_role_codes(row.get("ROLE_VALUE") or row.get("ROLE_CODE")):
                    _normalize_legacy_role(legacy_role, role_mapping, stats, table="pub_user", legacy_ref=user_id)
            elif status != "active":
                status = "disabled"
                binding_specs = []
            elif not binding_specs:
                issue_status = "unmatched"
                status = "unmatched"
                # warn: actor upserted with status='unmatched'; row recorded, just no org binding.
                stats.add_issue(
                    "missing_org_relationship",
                    "pub_user",
                    user_id,
                    {"account": account, "user_code": user_code},
                    severity="warn",
                )
            else:
                role_codes = sorted({item["role_code"] for item in binding_specs})
                main_org = next((item["org_code"] for item in binding_specs), main_org)

            actor_ref = iaf_sub or user_id
            payload = {
                "external_actor_id": actor_ref,
                "iaf_sub": iaf_sub,
                "legacy_actor_ref": user_id,
                "display_name": row.get("NAME") or account or user_id,
                "org_code": main_org,
                "role_codes": role_codes,
                "status": status,
                "source_ref": f"{legacy_system}:pub_user:{user_id}",
                "profile_json": _scrub_profile(
                    {
                        "legacy_actor_ref": user_id,
                        "legacy_user_code": user_code,
                        "account": account,
                        "preferred_username": _row_value(binding or {}, "PREFERRED_USERNAME", "USERNAME") or account,
                        "org_codes": sorted({item["org_code"] for item in binding_specs}),
                        "region_code": row.get("REGION_CODE"),
                        "binding_status": issue_status or "bound",
                        "batch_no": batch_no,
                    }
                ),
            }
            if dry_run:
                stats.bump_target("actor_projection")
                if binding_specs:
                    stats.target_counts["actor_org_role_binding"] = stats.target_counts.get("actor_org_role_binding", 0) + len(binding_specs)
            else:
                if iaf_sub and status == "active":
                    # Backfill → re-import: a real sub now exists for a user previously imported
                    # as iam_account_missing (keyed by legacy user_id). Rekey that row in place
                    # rather than letting upsert_actor insert a second sub-keyed row (dup users).
                    actor, _outcome = self.governance_repo.claim_legacy_actor_by_iaf(
                        iaf_sub=iaf_sub,
                        legacy_actor_ref=user_id,
                        claims_profile=payload["profile_json"],
                        token_role_codes=role_codes,
                        display_name=payload["display_name"],
                        org_code=main_org,
                        source_ref=payload["source_ref"],
                        tenant_id=self.tenant_id,
                    )
                else:
                    actor = self.governance_repo.upsert_actor(payload, tenant_id=self.tenant_id)
                if binding_specs and actor.status == "active":
                    self.governance_repo.sync_actor_bindings(actor, binding_specs, batch_no=batch_no)
            self._write_legacy_mapping(
                legacy_system=legacy_system,
                legacy_object_type="pub_user",
                legacy_object_ref=user_id,
                canonical_type="ActorProjectionRecord",
                canonical_ref=actor_ref,
                evidence={"account": account, "user_code": user_code, "binding_status": payload["profile_json"]["binding_status"]},
                dry_run=dry_run,
                stats=stats,
            )

        self._import_pub_role_permission_candidates(
            rows_by_table.get("pub_role_function", []),
            rows_by_table.get("pub_function", []),
            role_mapping,
            capability_index,
            stats,
            legacy_system,
            permission_kind="function",
            dry_run=dry_run,
        )
        self._import_pub_role_permission_candidates(
            rows_by_table.get("pub_role_resource", []),
            rows_by_table.get("pub_resource", []),
            role_mapping,
            capability_index,
            stats,
            legacy_system,
            permission_kind="resource",
            dry_run=dry_run,
        )
        _account_manifest_tables(rows_by_table, stats)

    def _import_pub_role_permission_candidates(
        self,
        relation_rows: list[dict[str, Any]],
        object_rows: list[dict[str, Any]],
        role_mapping: dict[str, dict[str, Any]],
        capability_index: dict[str, dict[str, Any]],
        stats: ImportStats,
        legacy_system: str,
        *,
        permission_kind: str,
        dry_run: bool,
    ) -> None:
        object_table = "pub_function" if permission_kind == "function" else "pub_resource"
        relation_table = "pub_role_function" if permission_kind == "function" else "pub_role_resource"
        object_index: dict[str, dict[str, Any]] = {}
        for row in object_rows:
            ref = _string_value(row, "ID", "CODE", "NAME_ID")
            if ref:
                object_index[ref] = row
            # Each object row is consumed as ACL evidence (indexed for role-permission
            # candidate emission below). Without this bump, strict table_accounting
            # sees source_rows>0 / handled_rows=0 and fail-closes the dump on
            # "unaccounted source row table(s)". Kind="attached" is recognized by
            # migration_batch._handled_table_totals; semantically each row is attached
            # to the ACL relation it backs.
            stats.bump(object_table, "attached")
        for row in relation_rows:
            legacy_role = _string_value(row, "ROLE_CODE", "ROLE_ID")
            permission_ref = _string_value(row, "FUNCTION_CODE", "FUNC_CODE", "RES_CODE", "RESOURCE_CODE", "RES_ID")
            role_code = _normalize_legacy_role(legacy_role, role_mapping, stats, table=relation_table, legacy_ref=f"{legacy_role}:{permission_ref}", allow_unmapped_role=True)
            mapped_role = role_code["role_code"] if role_code else legacy_role
            capability = capability_index.get(permission_ref)
            if not capability or not capability.get("capability_id"):
                # warn: relation row IS bumped; only the legacy_policy_mapping_candidate is skipped
                # (no capability_mapping_manifest entry for this permission). Per-row business info.
                stats.add_issue(
                    "unmapped_permission",
                    relation_table,
                    f"{legacy_role}:{permission_ref}",
                    {"role_ref": mapped_role, "permission_ref": permission_ref},
                    severity="warn",
                )
                stats.bump(relation_table)
                continue
            evidence = _scrub_profile(
                {
                    "role_ref": mapped_role,
                    "permission_ref": permission_ref,
                    "permission_kind": permission_kind,
                    "manifest_version": capability.get("manifest_version"),
                    "manifest_source_ref": capability.get("manifest_source_ref"),
                    "legacy_object": object_index.get(permission_ref, {}),
                }
            )
            self._write_projection(
                "legacy_policy_mapping_candidate",
                dry_run,
                lambda capability=capability, evidence=evidence, permission_ref=permission_ref, mapped_role=mapped_role: self.governance_repo.import_legacy_policy_candidate(
                    {
                        "legacy_system": legacy_system,
                        "legacy_permission_ref": permission_ref,
                        "legacy_role_ref": mapped_role,
                        "capability_id": capability["capability_id"],
                        "surface": capability.get("surface"),
                        "candidate_status": capability.get("candidate_status") or "pending_review",
                        "evidence_json": evidence,
                    },
                    tenant_id=self.tenant_id,
                ),
                stats,
            )
            stats.bump(relation_table)

    def _map_sys_governance(self, rows_by_table: dict[str, list[dict[str, Any]]], stats: ImportStats, legacy_system: str, *, dry_run: bool) -> None:
        tenant_payload = {
            "tenant_id": self.tenant_id,
            "tenant_name": "山东省默认租户" if self.tenant_id == DEFAULT_TENANT else self.tenant_id,
            "status": "active",
            "source_ref": f"{legacy_system}:tenant:{self.tenant_id}",
            "profile_json": {"import_source": "bsp_governance"},
        }
        if rows_by_table.get("sys_user") or rows_by_table.get("sys_department") or rows_by_table.get("sys_role") or rows_by_table.get("sys_region"):
            self._write_projection("tenant_projection", dry_run, lambda: self.governance_repo.upsert_tenant(tenant_payload, tenant_id=self.tenant_id), stats)
        departments = self._import_sys_departments(rows_by_table.get("sys_department", []), stats, legacy_system, dry_run=dry_run)
        self._import_sys_regions(rows_by_table.get("sys_region", []), stats, legacy_system, dry_run=dry_run)
        roles = self._import_sys_roles(rows_by_table.get("sys_role", []), stats, legacy_system, dry_run=dry_run)
        users = rows_by_table.get("sys_user", [])
        user_roles = _group_values(rows_by_table.get("sys_user_role", []), ("USER_ID", "USERID", "SYS_USER_ID"), ("ROLE_ID", "ROLEID", "SYS_ROLE_ID"))
        user_departments = _group_values(rows_by_table.get("sys_user_department", []), ("USER_ID", "USERID", "SYS_USER_ID"), ("DEPT_ID", "DEPARTMENT_ID", "ORG_ID", "DEPT_CODE"))
        binding_index = _binding_index(rows_by_table.get("iaf_binding_manifest", []))
        permission_index = _permission_index(rows_by_table.get("sys_permission", []), stats)
        capability_index = _capability_mapping_index(rows_by_table.get("capability_mapping_manifest", []), stats)

        for _row in rows_by_table.get("sys_user_role", []):
            stats.bump("sys_user_role")
        for _row in rows_by_table.get("sys_user_department", []):
            stats.bump("sys_user_department")

        for row in users:
            user_id = _string_value(row, "ID", "USER_ID", "USERID", "SYS_USER_ID")
            account = _string_value(row, "ACCOUNT", "USERNAME", "LOGIN_NAME", "USER_NAME")
            if not user_id:
                stats.add_issue("missing_actor_ref", "sys_user", account, {"reason": "missing_user_id"})
                stats.bump("sys_user")
                continue
            role_codes = [roles[role_id]["role_code"] for role_id in user_roles.get(user_id, []) if role_id in roles]
            org_codes = _org_codes_for_user(row, user_departments.get(user_id, []), departments)
            binding = binding_index.get(f"id:{user_id}") or binding_index.get(f"account:{account}")
            iaf_sub = _normalize_iaf_sub(_string_value(binding or {}, "IAF_SUB", "SUB", "IAM_SUB", "USER_SUB"))
            status = _status_flag(_row_value(row, "STATUS", "ENABLED", "STATE"))
            issue_status = None
            if not iaf_sub:
                issue_status = "iam_account_missing"
                status = "iam_account_missing"
                role_codes = []
                # warn: row IS upserted with sentinel status; same as pub_user path.
                stats.add_issue("iam_account_missing", "sys_user", user_id, {"account": account}, severity="warn")
            elif not org_codes:
                issue_status = "unmatched"
                status = "unmatched"
                role_codes = []
                # warn: row IS upserted with status='unmatched'.
                stats.add_issue("missing_org_relationship", "sys_user", user_id, {"account": account}, severity="warn")
            actor_ref = iaf_sub or user_id
            payload = {
                "external_actor_id": actor_ref,
                "iaf_sub": iaf_sub,
                "legacy_actor_ref": user_id,
                "display_name": _row_value(row, "DISPLAY_NAME", "REAL_NAME", "NAME", "NICK_NAME") or account or user_id,
                "org_code": org_codes[0] if org_codes else None,
                "role_codes": role_codes,
                "status": status,
                "source_ref": f"{legacy_system}:sys_user:{user_id}",
                "profile_json": _scrub_profile(
                    {
                        "legacy_actor_ref": user_id,
                        "account": account,
                        "preferred_username": _row_value(binding or {}, "PREFERRED_USERNAME", "USERNAME") or account,
                        "phone": _row_value(row, "PHONE", "TEL"),
                        "mobile": _row_value(row, "MOBILE", "PHONE_NUMBER"),
                        "email": _row_value(row, "EMAIL", "MAIL"),
                        "org_codes": org_codes,
                        "region_code": _row_value(row, "REGION_CODE", "REGION_ID"),
                        "binding_status": issue_status or "bound",
                    }
                ),
            }
            self._write_projection("actor_projection", dry_run, lambda payload=payload: self.governance_repo.upsert_actor(payload, tenant_id=self.tenant_id), stats)
            if org_codes and role_codes:
                stats.target_counts["actor_org_role_binding"] = stats.target_counts.get("actor_org_role_binding", 0) + len(role_codes)
            self._write_legacy_mapping(
                legacy_system=legacy_system,
                legacy_object_type="sys_user",
                legacy_object_ref=user_id,
                canonical_type="ActorProjectionRecord",
                canonical_ref=actor_ref,
                evidence={"account": account, "binding_status": payload["profile_json"]["binding_status"]},
                dry_run=dry_run,
                stats=stats,
            )
            stats.bump("sys_user")

        self._import_role_permission_candidates(
            rows_by_table.get("sys_role_permission", []),
            roles,
            permission_index,
            capability_index,
            stats,
            legacy_system,
            dry_run=dry_run,
        )
        _account_relation_tables(rows_by_table, stats)
        _account_manifest_tables(rows_by_table, stats)

    def _import_sys_departments(self, rows: list[dict[str, Any]], stats: ImportStats, legacy_system: str, *, dry_run: bool) -> dict[str, dict[str, str]]:
        departments: dict[str, dict[str, str]] = {}
        pending: list[tuple[dict[str, Any], str, str, str | None]] = []
        for row in rows:
            department_id = _string_value(row, "ID", "DEPT_ID", "DEPARTMENT_ID", "ORG_ID")
            org_code = _string_value(row, "CODE", "ORG_CODE", "DEPT_CODE", "DEPARTMENT_CODE") or department_id
            if not department_id or not org_code:
                stats.add_issue("missing_org_relationship", "sys_department", department_id or org_code, {"reason": "missing_department_id_or_code"})
                stats.bump("sys_department")
                continue
            parent_ref = _string_value(row, "PARENT_CODE", "PARENT_ORG_CODE", "PARENT_ID", "PARENT_DEPT_ID")
            departments[department_id] = {"org_code": org_code, "department_id": department_id}
            pending.append((row, department_id, org_code, parent_ref))
        for row, department_id, org_code, parent_ref in pending:
            parent_org_code = departments.get(parent_ref or "", {}).get("org_code", parent_ref) if parent_ref else None
            payload = {
                "org_code": org_code,
                "org_name": _row_value(row, "NAME", "DEPT_NAME", "ORG_NAME") or org_code,
                "parent_org_code": parent_org_code,
                "region_code": _row_value(row, "REGION_CODE", "REGION_ID"),
                "status": _status_flag(_row_value(row, "STATUS", "ENABLED", "STATE")),
                "source_ref": f"{legacy_system}:sys_department:{department_id}",
                "profile_json": _scrub_profile({"legacy_department_id": department_id, "department_code": org_code}),
            }
            self._write_projection("org_projection", dry_run, lambda payload=payload: self.governance_repo.upsert_org(payload, tenant_id=self.tenant_id), stats)
            self._write_legacy_mapping(
                legacy_system=legacy_system,
                legacy_object_type="sys_department",
                legacy_object_ref=department_id,
                canonical_type="OrgProjectionRecord",
                canonical_ref=org_code,
                evidence={"org_code": org_code},
                dry_run=dry_run,
                stats=stats,
            )
            stats.bump("sys_department")
        return departments

    def _import_sys_regions(self, rows: list[dict[str, Any]], stats: ImportStats, legacy_system: str, *, dry_run: bool) -> dict[str, str]:
        regions: dict[str, str] = {}
        for row in rows:
            region_id = _string_value(row, "ID", "REGION_ID", "CODE", "REGION_CODE")
            region_code = _string_value(row, "CODE", "REGION_CODE") or region_id
            if not region_id or not region_code:
                stats.add_issue("missing_region_ref", "sys_region", region_id or region_code, {"reason": "missing_region_id_or_code"})
                stats.bump("sys_region")
                continue
            regions[region_id] = region_code
            payload = {
                "region_code": region_code,
                "region_name": _row_value(row, "NAME", "REGION_NAME") or region_code,
                "parent_region_code": _row_value(row, "PARENT_CODE", "PARENT_REGION_CODE", "PARENT_ID"),
                "region_level": _row_value(row, "GRADE", "LEVEL", "REGION_LEVEL"),
                "status": _status_flag(_row_value(row, "STATUS", "ENABLED", "STATE")),
                "source_ref": f"{legacy_system}:sys_region:{region_id}",
                "profile_json": _scrub_profile({"legacy_region_id": region_id}),
            }
            self._write_projection("region_projection", dry_run, lambda payload=payload: self.governance_repo.upsert_region(payload, tenant_id=self.tenant_id), stats)
            self._write_legacy_mapping(
                legacy_system=legacy_system,
                legacy_object_type="sys_region",
                legacy_object_ref=region_id,
                canonical_type="RegionProjectionRecord",
                canonical_ref=region_code,
                evidence={"region_code": region_code},
                dry_run=dry_run,
                stats=stats,
            )
            stats.bump("sys_region")
        return regions

    def _import_sys_roles(self, rows: list[dict[str, Any]], stats: ImportStats, legacy_system: str, *, dry_run: bool) -> dict[str, dict[str, str]]:
        roles: dict[str, dict[str, str]] = {}
        for row in rows:
            role_id = _string_value(row, "ID", "ROLE_ID", "SYS_ROLE_ID")
            role_code = _string_value(row, "ROLE_CODE", "CODE", "VALUE", "ROLE_KEY") or role_id
            if not role_id or not role_code:
                stats.add_issue("missing_role_ref", "sys_role", role_id or role_code, {"reason": "missing_role_id_or_code"})
                stats.bump("sys_role")
                continue
            roles[role_id] = {"role_code": role_code, "role_id": role_id}
            payload = {
                "role_code": role_code,
                "role_name": _row_value(row, "NAME", "ROLE_NAME") or role_code,
                "status": _status_flag(_row_value(row, "STATUS", "ENABLED", "STATE")),
                "source_ref": f"{legacy_system}:sys_role:{role_id}",
                "profile_json": _scrub_profile({"legacy_role_id": role_id}),
            }
            self._write_projection("role_projection", dry_run, lambda payload=payload: self.governance_repo.upsert_role(payload, tenant_id=self.tenant_id), stats)
            self._write_legacy_mapping(
                legacy_system=legacy_system,
                legacy_object_type="sys_role",
                legacy_object_ref=role_id,
                canonical_type="RoleProjectionRecord",
                canonical_ref=role_code,
                evidence={"role_code": role_code},
                dry_run=dry_run,
                stats=stats,
            )
            stats.bump("sys_role")
        return roles

    def _import_role_permission_candidates(
        self,
        rows: list[dict[str, Any]],
        roles: dict[str, dict[str, str]],
        permissions: dict[str, dict[str, Any]],
        capability_index: dict[str, dict[str, Any]],
        stats: ImportStats,
        legacy_system: str,
        *,
        dry_run: bool,
    ) -> None:
        for row in rows:
            role_id = _string_value(row, "ROLE_ID", "SYS_ROLE_ID")
            permission_id = _string_value(row, "PERMISSION_ID", "PERM_ID", "AUTHORITY_ID")
            role_code = roles.get(role_id, {}).get("role_code", role_id)
            permission = permissions.get(permission_id) or {"permission_ref": permission_id, "permission_id": permission_id}
            permission_ref = str(permission.get("permission_ref") or permission_id)
            capability = capability_index.get(permission_ref) or capability_index.get(permission_id)
            if not capability or not capability.get("capability_id"):
                # warn: relation row IS bumped; only legacy_policy_mapping_candidate emission
                # skipped because capability_mapping_manifest doesn't cover this permission.
                stats.add_issue(
                    "unmapped_permission",
                    "sys_role_permission",
                    f"{role_id}:{permission_id}",
                    {"role_ref": role_code, "permission_ref": permission_ref},
                    severity="warn",
                )
                stats.bump("sys_role_permission")
                continue
            capability_id = str(capability["capability_id"])
            evidence = _scrub_profile(
                {
                    "role_ref": role_code,
                    "permission_ref": permission_ref,
                    "permission_name": permission.get("permission_name"),
                    "manifest_version": capability.get("manifest_version"),
                    "manifest_source_ref": capability.get("manifest_source_ref"),
                }
            )
            self._write_projection(
                "legacy_policy_mapping_candidate",
                dry_run,
                lambda capability=capability, evidence=evidence, permission_ref=permission_ref, role_code=role_code: self.governance_repo.import_legacy_policy_candidate(
                    {
                        "legacy_system": legacy_system,
                        "legacy_permission_ref": permission_ref,
                        "legacy_role_ref": role_code,
                        "capability_id": capability["capability_id"],
                        "surface": capability.get("surface"),
                        "candidate_status": capability.get("candidate_status") or "pending_review",
                        "evidence_json": evidence,
                    },
                    tenant_id=self.tenant_id,
                ),
                stats,
            )
            self._write_legacy_mapping(
                legacy_system=legacy_system,
                legacy_object_type="sys_permission",
                legacy_object_ref=permission_ref,
                canonical_type="capability",
                canonical_ref=capability_id,
                evidence=evidence,
                dry_run=dry_run,
                stats=stats,
            )
            stats.bump("sys_role_permission")

    def _write_projection(self, target: str, dry_run: bool, writer: Any, stats: ImportStats) -> None:
        stats.bump_target(target)
        if not dry_run:
            writer()

    def _write_legacy_mapping(
        self,
        *,
        legacy_system: str,
        legacy_object_type: str,
        legacy_object_ref: str,
        canonical_type: str,
        canonical_ref: str,
        evidence: dict[str, Any] | None = None,
        dry_run: bool = False,
        stats: ImportStats | None = None,
    ) -> None:
        if stats is not None:
            stats.bump_target("legacy_object_mapping")
        if dry_run:
            return
        self.legacy_repo.upsert_mapping(
            {
                "source_ref": f"{legacy_system}:{legacy_object_type}:{legacy_object_ref}",
                "legacy_system": legacy_system,
                "legacy_object_type": legacy_object_type,
                "legacy_object_ref": legacy_object_ref,
                "canonical_type": canonical_type,
                "canonical_ref": canonical_ref,
                "evidence_json": _scrub_profile(evidence or {}),
            },
            tenant_id=self.tenant_id,
        )


def _status_flag(raw: Any) -> str:
    normalized = str(raw).lower() if raw is not None else ""
    if raw in ("1", 1, True) or normalized in {"active", "enabled", "enable", "y", "yes"}:
        return "active"
    if raw in ("0", 0, False) or normalized in {"inactive", "disabled", "disable", "n", "no"}:
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


def _split_pub_organ_role_codes(raw: Any) -> list[str]:
    """BSP pub_user_organ_role.ROLE_CODE 多角色拼接：schema comment 明确 '以#号分隔'。
    宽容地兼容 ',' / ';' / '|' 分隔以防客户场景偏离，但 '#' 是文档化的主分隔。"""
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw if item]
    text = str(raw)
    # 一次拆多种分隔符；不直接 replace 多次，保留稳定顺序便于后续 dedup。
    for sep in ("#", ";", "|"):
        text = text.replace(sep, ",")
    return [piece.strip() for piece in text.split(",") if piece.strip()]


def _lower_keys(row: dict[str, Any]) -> dict[str, Any]:
    return {str(key).lower(): value for key, value in row.items()}


def _row_value(row: dict[str, Any], *names: str) -> Any:
    if not row:
        return None
    lowered = _lower_keys(row)
    for name in names:
        if name in row:
            return row[name]
        value = lowered.get(name.lower())
        if value not in (None, ""):
            return value
    return None


def _string_value(row: dict[str, Any], *names: str) -> str:
    value = _row_value(row, *names)
    return str(value) if value not in (None, "") else ""


def _scrub_row(row: dict[str, Any], denylist: set[str] | None = None) -> dict[str, Any]:
    deny = {item.lower() for item in (denylist or set())} | REAL_SECRET_FIELDS
    return {key: value for key, value in row.items() if not _is_real_secret_key(key, deny)}


def _scrub_profile(profile: dict[str, Any]) -> dict[str, Any]:
    scrubbed = {key: value for key, value in profile.items() if not _is_real_secret_key(key, REAL_SECRET_FIELDS)}
    return safe_json(scrubbed)


def _is_real_secret_key(key: Any, denylist: set[str]) -> bool:
    lowered = str(key).lower()
    return lowered in denylist or any(part in lowered for part in ("password", "token", "client_secret", "verification_code", "session", "cookie"))


def _group_values(rows: list[dict[str, Any]], key_fields: tuple[str, ...], value_fields: tuple[str, ...]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for row in rows:
        key = _string_value(row, *key_fields)
        value = _string_value(row, *value_fields)
        if key and value:
            out.setdefault(key, []).append(value)
    return out


def _org_codes_for_user(row: dict[str, Any], department_refs: list[str], departments: dict[str, dict[str, str]]) -> list[str]:
    direct = _string_value(row, "ORG_CODE", "DEPT_CODE", "DEPARTMENT_CODE")
    direct_id = _string_value(row, "ORG_ID", "DEPT_ID", "DEPARTMENT_ID")
    refs = [*department_refs, direct_id, direct]
    out: list[str] = []
    for ref in refs:
        if not ref:
            continue
        code = departments.get(ref, {}).get("org_code", ref if direct and ref == direct else "")
        if code and code not in out:
            out.append(code)
    return out


def _binding_index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        legacy_user_id = _string_value(row, "LEGACY_USER_ID", "USER_ID", "SYS_USER_ID")
        user_code = _string_value(row, "LEGACY_USER_CODE", "USER_CODE")
        account = _string_value(row, "ACCOUNT", "USERNAME", "PREFERRED_USERNAME")
        if legacy_user_id:
            out[f"id:{legacy_user_id}"] = row
        if user_code:
            out[f"code:{user_code}"] = row
        if account:
            out[f"account:{account}"] = row
    return out


def _role_mapping_index(rows: list[dict[str, Any]], stats: ImportStats) -> dict[str, dict[str, Any]]:
    # All `unmapped_role` calls here are warn-severity: the role_mapping_manifest row
    # is bumped (accounted for); only the index entry is skipped on bad metadata.
    # Downstream per-row will surface "missing_role_mapping" with same severity.
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        legacy_role_ref = _string_value(row, "LEGACY_ROLE_REF", "LEGACY_ROLE_CODE", "ROLE_CODE", "ROLE_VALUE", "VALUE")
        if not legacy_role_ref:
            stats.add_issue("unmapped_role", "role_mapping_manifest", "", {"reason": "missing_legacy_role_ref"}, severity="warn")
            stats.bump("role_mapping_manifest")
            continue
        target_type = str(_row_value(row, "TARGET_TYPE") or "role").lower()
        target_role_code = _string_value(row, "TARGET_ROLE_CODE")
        target_tag = _string_value(row, "TARGET_TAG")
        if target_type == "tag" and target_tag not in {TAG_LEAD_DEPT}:
            stats.add_issue("unmapped_role", "role_mapping_manifest", legacy_role_ref, {"reason": "unsupported_target_tag", "target_tag": target_tag}, severity="warn")
            stats.bump("role_mapping_manifest")
            continue
        if target_type == "role" and target_role_code in _FORBIDDEN_IMPORT_ROLE_CODES:
            stats.add_issue("unmapped_role", "role_mapping_manifest", legacy_role_ref, {"reason": "forbidden_technical_role", "target_role_code": target_role_code}, severity="warn")
            stats.bump("role_mapping_manifest")
            continue
        out[legacy_role_ref] = {
            "target_type": target_type,
            "target_role_code": target_role_code,
            "target_tag": target_tag or None,
            "confidence": _row_value(row, "CONFIDENCE"),
        }
        stats.bump("role_mapping_manifest")
    return out


def _normalize_legacy_role(
    legacy_role: str,
    role_mapping: dict[str, dict[str, Any]],
    stats: ImportStats,
    *,
    table: str,
    legacy_ref: str,
    allow_unmapped_role: bool = False,
) -> dict[str, Any] | None:
    # All `unmapped_role` issues here are warn-severity: the caller's row is still
    # imported (with empty role_codes or fallback); this function only signals
    # "this particular legacy role can't be normalized" per-call, not a row drop.
    normalized = str(legacy_role or "").strip()
    if not normalized:
        return None
    lowered = normalized.lower()
    if lowered in LEGACY_ROLE_CODES:
        stats.add_issue("unmapped_role", table, legacy_ref, {"reason": "legacy_r1_r8_blocked", "legacy_role": normalized}, severity="warn")
        return None
    mapping = role_mapping.get(normalized)
    if mapping is None:
        stats.add_issue("unmapped_role", table, legacy_ref, {"reason": "missing_role_mapping", "legacy_role": normalized}, severity="warn")
        return None
    target_type = str(mapping.get("target_type") or "role")
    target_role_code = str(mapping.get("target_role_code") or "")
    if target_type == "tag":
        if target_role_code not in _PRODUCT_ROLE_ALLOWLIST:
            stats.add_issue("unmapped_role", table, legacy_ref, {"reason": "tag_requires_product_role", "target_role_code": target_role_code}, severity="warn")
            return None
        tag = mapping.get("target_tag")
        return {"role_code": target_role_code, "tags_json": {tag: True} if tag else {}}
    if target_role_code in _FORBIDDEN_IMPORT_ROLE_CODES:
        stats.add_issue("unmapped_role", table, legacy_ref, {"reason": "forbidden_technical_role", "legacy_role": normalized}, severity="warn")
        return None
    if target_role_code not in _PRODUCT_ROLE_ALLOWLIST:
        stats.add_issue("unmapped_role", table, legacy_ref, {"reason": "role_not_in_product_allowlist", "legacy_role": normalized, "target_role_code": target_role_code}, severity="warn")
        return None if not allow_unmapped_role else {"role_code": target_role_code, "tags_json": {}}
    return {"role_code": target_role_code, "tags_json": {}}


def _normalize_role_list(
    legacy_roles: list[str],
    role_mapping: dict[str, dict[str, Any]],
    stats: ImportStats,
    *,
    table: str,
    legacy_ref: str,
) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    seen: set[tuple[str, str]] = set()
    for legacy_role in legacy_roles:
        normalized = _normalize_legacy_role(legacy_role, role_mapping, stats, table=table, legacy_ref=legacy_ref)
        if normalized is None:
            continue
        key = (normalized["role_code"], str(sorted((normalized.get("tags_json") or {}).items())))
        if key in seen:
            continue
        seen.add(key)
        out.append((normalized["role_code"], normalized.get("tags_json") or {}))
    return out


def _permission_index(rows: list[dict[str, Any]], stats: ImportStats) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        permission_id = _string_value(row, "ID", "PERMISSION_ID", "PERM_ID", "AUTHORITY_ID")
        permission_ref = _string_value(row, "PERMISSION_CODE", "PERM_CODE", "CODE", "AUTHORITY", "VALUE") or permission_id
        payload = {"permission_id": permission_id, "permission_ref": permission_ref, "permission_name": _row_value(row, "NAME", "PERMISSION_NAME", "TITLE")}
        if not permission_id and not permission_ref:
            stats.add_issue("missing_permission_ref", "sys_permission", "", {"reason": "missing_permission_id_or_code"})
            stats.bump("sys_permission")
            continue
        if permission_id:
            out[permission_id] = payload
        if permission_ref:
            out[permission_ref] = payload
        stats.bump("sys_permission")
    return out


def _capability_mapping_index(rows: list[dict[str, Any]], stats: ImportStats) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        permission_refs = {
            _string_value(row, "LEGACY_PERMISSION_REF", "PERMISSION_REF", "PERMISSION_CODE", "PERM_CODE", "CODE"),
            _string_value(row, "PERMISSION_ID", "PERM_ID", "LEGACY_PERMISSION_ID"),
        }
        capability_id = _string_value(row, "CAPABILITY_ID", "CAPABILITY_SLUG", "SKILL_ID")
        if not capability_id:
            stats.bump("capability_mapping_manifest")
            continue
        payload = {
            "capability_id": capability_id,
            "surface": _row_value(row, "SURFACE"),
            "candidate_status": _row_value(row, "CANDIDATE_STATUS"),
            "manifest_version": _row_value(row, "MANIFEST_VERSION", "VERSION"),
            "manifest_source_ref": _row_value(row, "MANIFEST_SOURCE_REF", "SOURCE_REF"),
        }
        for permission_ref in permission_refs:
            if permission_ref:
                out[str(permission_ref)] = payload
        stats.bump("capability_mapping_manifest")
    return out


def _account_relation_tables(rows_by_table: dict[str, list[dict[str, Any]]], stats: ImportStats) -> None:
    for table_name in ("sys_user_role", "sys_user_department"):
        accounted = stats.counts.get(f"{table_name}.imported", 0)
        missing = len(rows_by_table.get(table_name, [])) - accounted
        for _ in range(max(missing, 0)):
            stats.bump(table_name)


def _account_manifest_tables(rows_by_table: dict[str, list[dict[str, Any]]], stats: ImportStats) -> None:
    accounted = stats.counts.get("iaf_binding_manifest.imported", 0)
    for _ in range(max(len(rows_by_table.get("iaf_binding_manifest", [])) - accounted, 0)):
        stats.bump("iaf_binding_manifest")
