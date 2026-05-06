"""dsp_connect → ExternalObjectMappingRecord (national platform / cascade receipts).

Each dc_* row represents a sync receipt or external mapping between the local
canonical aggregate and an external system (typically the national / 上级 platform).
We don't try to reconstruct the canonical aggregate from these rows (that's the
job of the catalog/exchange/objection mappers); we only record the mapping so
queries can resolve "which external_object_id corresponds to my local resource".

Excluded by design (non-mappable / contains secrets):
  dc_datasource             — connection strings (real secrets)
  batch_job_*               — Spring Batch metadata, not business state

Excluded by emptiness in sample dump (preserved as `stats.skip` for visibility):
  dc_to_subscribe / dc_supply_baseinfo / dc_sync_job (non-zero rows but no
  consistent local linkage in the sample) — handled as best-effort.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from zw_brain.adapters.legacy._common import ImportStats, finish_run, schema_from_dump_name
from zw_brain.adapters.legacy.parser import MysqldumpParser
from zw_brain.adapters.legacy.tenant_normalizer import DEFAULT_TENANT, legacy_system_for
from zw_brain.domain.repositories.external_adapter import ExternalAdapterRepository
from zw_brain.shared.sanitization import safe_json

# table → (local_aggregate_type, local_id_field, primary_id_field, direction)
# `local_id_field` resolves the legacy row's reference to the local canonical thing
# (e.g. dc_resource_apply_info.local_apply_id → ApplicationRecord); when empty, we
# leave local_aggregate_id blank and rely on the dc_* row's own id as the external_id.
_TABLE_CONFIG: dict[str, tuple[str, str | None, str, str]] = {
    "dc_catalog":              ("catalog",                "local_cata_id",    "id",  "inbound"),
    "dc_catalog_group":        ("catalog_group",          None,                "id",  "inbound"),
    "dc_catalog_item":         ("catalog_item",           "local_column_id",   "id",  "inbound"),
    "dc_organ":                ("org",                    None,                "id",  "inbound"),
    "dc_organ_mapping":        ("org",                    "local_org_code",    "id",  "inbound"),
    "dc_area_mapping":         ("region",                 "local_region_code", "id",  "inbound"),
    "dc_objection_base_info":  ("objection",              "local_objection_id","id",  "outbound"),
    "dc_objection_apply":      ("objection",              "local_objection_id","id",  "outbound"),
    "dc_objection_catalog":    ("objection",              "local_objection_id","id",  "outbound"),
    "dc_objection_resource":   ("objection",              "local_objection_id","id",  "outbound"),
    "dc_objection_use":        ("objection",              "local_objection_id","id",  "outbound"),
    "dc_objection_flow":       ("objection_flow",         "local_objection_id","id",  "outbound"),
    "dc_objection_accept_audit":("objection_audit",       None,                "id",  "outbound"),
    "dc_resource_apply_info":  ("application",            "local_apply_id",    "id",  "outbound"),
    "dc_resource_apply_info_province":("application",     "local_apply_id",    "id",  "outbound"),
    "dc_resource_apply_audit": ("application_audit",      None,                "id",  "outbound"),
    "dc_resource_apply_audit_province":("application_audit", None,             "id",  "outbound"),
    "dc_resource_apply_accept_audit":("application_audit", None,               "id",  "outbound"),
    "dc_resource_base_info":   ("resource",               "local_resource_id", "id",  "outbound"),
    "dc_resource_base_info_total":("resource",            "local_resource_id", "id",  "outbound"),
    "dc_resource_table_detail":("resource_table",         None,                "id",  "outbound"),
    "dc_resource_table_detail_total":("resource_table",   None,                "id",  "outbound"),
    "dc_resource_table_column":("resource_column",        None,                "id",  "outbound"),
    "dc_resource_table_column_total":("resource_column",  None,                "id",  "outbound"),
    "dc_resource_file_detail": ("resource_file",          None,                "id",  "outbound"),
    "dc_resource_file_detail_total":("resource_file",     None,                "id",  "outbound"),
    "dc_resource_api_detail":  ("resource_api",           None,                "id",  "outbound"),
    "dc_resource_api_detail_total":("resource_api",       None,                "id",  "outbound"),
    "dc_resource_api_auth_info":("resource_api_auth",     None,                "id",  "outbound"),
    "dc_subscribe":            ("delivery_subscription",  "local_sub_id",      "id",  "outbound"),
    "dc_subscribe_table":      ("delivery_subscription",  None,                "id",  "outbound"),
    "dc_subscribe_folder":     ("delivery_subscription",  None,                "id",  "outbound"),
    "dc_to_subscribe":         ("delivery_subscription",  None,                "id",  "inbound"),
    "dc_require":              ("application",            "local_require_id",  "id",  "outbound"),
    "dc_require_antecedent":   ("application_require",    None,                "id",  "outbound"),
    "dc_require_column":       ("application_require_column", None,            "id",  "outbound"),
    "dc_require_resource":     ("application_require_resource", None,          "id",  "outbound"),
    "dc_example_infoitem":     ("topic_package_item",     None,                "id",  "outbound"),
    "dc_example_matters":      ("topic_package_matter",   None,                "id",  "outbound"),
    "dc_example_resource":     ("topic_package_resource", None,                "id",  "outbound"),
    "dc_supply_baseinfo":      ("supply",                 None,                "id",  "outbound"),
    "dc_sync_job":             ("sync_job",               None,                "id",  "outbound"),
    "dc_opt_log":              ("operation_log",          None,                "id",  "outbound"),
    "dc_system":               ("external_system",        None,                "id",  "inbound"),
}
# Tables explicitly excluded (real secrets / no business value)
_EXCLUDED = {"dc_datasource"}


class ConnectMapper:
    HANDLED_TABLES = set(_TABLE_CONFIG.keys())
    ADAPTER_SLUG = "legacy.dataconnect.import"
    EXTERNAL_SYSTEM = "national_platform"

    def __init__(self, *, tenant_id: str = DEFAULT_TENANT):
        self.tenant_id = tenant_id
        # ConnectMapper writes ExternalObjectMappingRecord (national / 上级 platform
        # ↔ local canonical), NOT LegacyObjectMappingRecord (old DSP DB ↔ zw-brain).
        # The two are different audit trails — see legacy-import-mapping-v1.md §〇.
        self.adapter_repo = ExternalAdapterRepository()

    def import_dump(self, dump_path: Path) -> ImportStats:
        schema = schema_from_dump_name(dump_path.name)
        legacy_system = legacy_system_for(schema)
        stats = ImportStats(schema=schema, dump_path=dump_path)
        started_at = datetime.now(UTC)

        for table, row in MysqldumpParser(dump_path).iter_rows():
            if table in _EXCLUDED:
                stats.skip(f"{table}.excluded_secret")
                continue
            if table not in self.HANDLED_TABLES:
                stats.skip(table)
                continue
            try:
                self._map_row(table, row, legacy_system)
                stats.bump(table)
            except KeyError as exc:
                stats.bump(table, "errors")
                key = f"{table}.missing_field:{exc.args[0]}"
                stats.skipped[key] = stats.skipped.get(key, 0) + 1

        finish_run(self.adapter_repo, stats, adapter_slug=self.ADAPTER_SLUG, dump_path=dump_path, started_at=started_at, tenant_id=self.tenant_id)
        return stats

    def _map_row(self, table: str, row: dict[str, Any], legacy_system: str) -> None:
        local_type, local_id_field, pk_field, direction = _TABLE_CONFIG[table]
        external_id = str(row.get(pk_field) or row.get("id") or "")
        if not external_id:
            return
        local_id = ""
        if local_id_field:
            local_id = str(row.get(local_id_field) or "")
        self.adapter_repo.upsert_mapping(
            {
                "external_system": self.EXTERNAL_SYSTEM,
                "direction": direction,
                "local_aggregate_type": local_type,
                "local_aggregate_id": local_id,
                "legacy_table": table,
                "legacy_id": external_id,
                "external_object_type": table.removeprefix("dc_"),
                "external_object_id": external_id,
                "status": "received",
                # safe_json drops bytes (from hex literals) and any sensitive
                # keys that crept in (password/token/key/credential), and also
                # protects the JSON serializer from non-serializable types.
                "extra_json": safe_json(row),
            },
            tenant_id=self.tenant_id,
        )
