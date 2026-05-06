"""Catalog & metadata mapper: dsp_catalog + dsp_metaresource → CatalogEntry + ResourceAsset.

Steps 2–4 of the 8-step bridging chain (after governance):
    2. rc_resource (dsp_metaresource) → ResourceAssetRecord
    3. data_catalog (dsp_catalog) → CatalogEntryRecord
       data_catalog_column (dsp_catalog) → CatalogItemRecord
    4. data_resource (dsp_catalog) → ResourceAssetRecord (合流 with rc_resource)

The two dumps are imported by the same mapper class but run independently
(`import_dump(dsp_metaresource_dump)` then `import_dump(dsp_catalog_dump)`),
because each dump has its own AdapterRunRecord.

Lifecycle status mapping is conservative — preserves the legacy intent without inventing
new states; consumers can still re-bin via decision_payload_json. Dropped at row boundary:
data_resource.del_desc / stop_desc are kept (audit content), but no real secrets exist
in these tables.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from zw_brain.adapters.legacy._common import (
    ImportStats,
    coerce_int,
    coerce_time,
    finish_run,
    schema_from_dump_name,
)
from zw_brain.adapters.legacy.parser import MysqldumpParser
from zw_brain.adapters.legacy.tenant_normalizer import DEFAULT_TENANT, legacy_system_for
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.domain.repositories.external_adapter import ExternalAdapterRepository
from zw_brain.domain.repositories.resource_api import ResourceApiRepository

# Legacy `data_catalog.status` codes per CREATE TABLE COMMENT
CATALOG_STATUS_TO_LIFECYCLE: dict[Any, str] = {
    0: "draft",
    1: "pending_review",
    2: "approved_pending_publish",
    3: "rejected",
    4: "active",
    5: "retired",
}
# Legacy `data_resource.status` & `rc_resource.status` codes
RESOURCE_STATUS_TO_LIFECYCLE: dict[Any, str] = {
    1: "draft",
    2: "pending_review",
    3: "approved_pending_publish",
    4: "active",
    5: "revoked",
    6: "suspended",
    7: "expired",
    20: "pending_review",
    21: "pending_review",
    30: "approved_pending_publish",
    31: "approved_pending_publish",
    40: "rejected",
    41: "rejected",
    -1: "deleted",
}


class CatalogMetadataMapper:
    HANDLED_SCHEMAS = ("dsp_catalog", "dsp_metaresource")
    HANDLED_TABLES = {"data_catalog", "data_catalog_column", "data_resource", "rc_resource"}
    ADAPTER_SLUG = "legacy.catalog_metadata.import"

    def __init__(self, *, tenant_id: str = DEFAULT_TENANT):
        self.tenant_id = tenant_id
        self.catalog_repo = CatalogRepository()
        self.resource_repo = ResourceApiRepository()
        self.adapter_repo = ExternalAdapterRepository()

    def import_dump(self, dump_path: Path) -> ImportStats:
        # Schema is encoded in the dump filename: dump-<schema>-<ts>.sql
        schema = schema_from_dump_name(dump_path.name)
        stats = ImportStats(schema=schema, dump_path=dump_path)
        legacy_system = legacy_system_for(schema)
        started_at = datetime.now(UTC)

        for table, row in MysqldumpParser(dump_path).iter_rows():
            if table not in self.HANDLED_TABLES:
                stats.skip(table)
                continue
            try:
                if table == "data_catalog":
                    self._map_data_catalog(row, legacy_system)
                elif table == "data_catalog_column":
                    self._map_data_catalog_column(row, legacy_system)
                elif table == "data_resource":
                    self._map_data_resource(row, legacy_system)
                elif table == "rc_resource":
                    self._map_rc_resource(row, legacy_system)
                stats.bump(table)
            except KeyError as exc:
                stats.bump(table, "errors")
                stats.skipped[f"{table}.missing_field:{exc.args[0]}"] = (
                    stats.skipped.get(f"{table}.missing_field:{exc.args[0]}", 0) + 1
                )

        finish_run(self.adapter_repo, stats, adapter_slug=self.ADAPTER_SLUG, dump_path=dump_path, started_at=started_at, tenant_id=self.tenant_id)
        return stats

    # ------------------------------------------------------------------
    # per-table handlers
    # ------------------------------------------------------------------

    def _map_data_catalog(self, row: dict[str, Any], legacy_system: str) -> None:
        cata_id = row["cata_id"]
        cata_code = row.get("cata_code") or cata_id
        catalog_code = str(cata_code)
        lifecycle = CATALOG_STATUS_TO_LIFECYCLE.get(row.get("status"), "draft")
        contact = {
            "contact_name": row.get("contact_name"),
            "contact_email": row.get("contact_email"),
            "contact_phone": row.get("contact_phone"),
            "creator_name": row.get("creator_name"),
        }
        self.catalog_repo.upsert_from_resource(
            {
                "id": catalog_code,
                "name": row.get("cata_title") or catalog_code,
                "status": lifecycle,
                "provider": row.get("org_code"),
                "region_code": row.get("region_code"),
                "source_ref": f"{legacy_system}:data_catalog:{cata_id}",
                "legacy_object_ref": cata_id,
                "summary": {
                    "org_name": row.get("org_name"),
                    "internal_org_name": row.get("internal_org_name"),
                    "description": row.get("description"),
                    "resource_format": row.get("resource_format"),
                    "shared_type": row.get("shared_type"),
                    "shared_condition": row.get("shared_condition"),
                    "shared_way": row.get("shared_way"),
                    "open_type": row.get("open_type"),
                    "open_condition": row.get("open_condition"),
                    "update_cycle": row.get("update_cycle"),
                    "catalog_type": row.get("catalog_type"),
                    "base_group_id": row.get("base_group_id"),
                    "theme_group_id": row.get("theme_group_id"),
                    "cata_version": row.get("cata_version"),
                    "published_time": coerce_time(row.get("published_time")),
                    "visit_count": row.get("visit_count"),
                    "file_count": row.get("file_count"),
                    "api_count": row.get("api_count"),
                    "table_count": row.get("table_count"),
                    "folder_count": row.get("folder_count"),
                    "contact": contact,
                },
            },
            tenant_id=self.tenant_id,
        )

    def _map_data_catalog_column(self, row: dict[str, Any], legacy_system: str) -> None:
        cata_id = row["cata_id"]
        column_id = row["column_id"]
        # CatalogItemRecord.catalog_code expects the new catalog_code (== old cata_code).
        # We don't have cata_code here, so we use cata_id as the code, matching the
        # convention chosen in _map_data_catalog (which falls back to cata_id when
        # cata_code is empty). Mappers downstream can re-bind via legacy_object_mapping.
        self.catalog_repo.upsert_item(
            {
                "item_code": column_id,
                "catalog_code": cata_id,
                "title": row.get("name_cn") or column_id,
                "item_kind": "field",
                "display_order": coerce_int(row.get("order_id"), 0),
                "source_ref": f"{legacy_system}:data_catalog_column:{column_id}",
                "summary_json": {
                    "name_en": row.get("name_en"),
                    "data_format": row.get("data_format"),
                    "length": row.get("length"),
                    "sensitive_level": row.get("sensitive_level"),
                    "is_key": row.get("is_key"),
                    "is_major": row.get("is_major"),
                    "is_open": row.get("is_open"),
                    "share_condition_type": row.get("share_condition_type"),
                    "share_condition": row.get("share_condition"),
                    "element_id": row.get("element_id"),
                    "element_name": row.get("element_name"),
                    "data_dict_code": row.get("data_dict_code"),
                    "data_dict_name": row.get("data_dict_name"),
                    "is_standard": row.get("is_standard"),
                    "standard_column_id": row.get("standard_column_id"),
                    "remark": row.get("remark"),
                    "open_condition": row.get("open_condition"),
                },
            },
            tenant_id=self.tenant_id,
        )

    def _map_data_resource(self, row: dict[str, Any], legacy_system: str) -> None:
        res_id = row["res_id"]
        resource_code = str(row.get("res_code") or res_id)
        lifecycle = RESOURCE_STATUS_TO_LIFECYCLE.get(coerce_int(row.get("status")), "draft")
        resource_kind = _normalize_resource_kind(row.get("res_type"))
        self.resource_repo.upsert_asset(
            {
                "resource_code": resource_code,
                "resource_kind": resource_kind,
                "title": row.get("res_name") or resource_code,
                "lifecycle_status": lifecycle,
                "owner_org_id": row.get("owner_org_id") or row.get("org_id"),
                "owner_org_snapshot_json": {
                    "org_id": row.get("org_id"),
                    "org_name": row.get("org_name"),
                    "owner_org_name": row.get("owner_org_name"),
                },
                "region_code": row.get("region_code"),
                "catalog_code": row.get("cata_id"),
                "access_policy_json": {
                    "share_type": row.get("share_type"),
                    "share_condition": row.get("share_condition"),
                    "open_type": row.get("open_type"),
                    "open_condition": row.get("open_condition"),
                    "inner_share_type": row.get("inner_share_type"),
                    "authorization_type": row.get("authorization_type"),
                    "allow_proxy": row.get("allow_proxy"),
                    "requiredfile": row.get("requiredfile"),
                },
                "qos_policy_json": {
                    "update_cycle": row.get("update_cycle"),
                    "validity_date": coerce_time(row.get("validity_date")),
                    "publish_date": coerce_time(row.get("publish_date")),
                    "register_date": coerce_time(row.get("register_date")),
                    "stop_or_start": row.get("stop_or_start"),
                    "stop_time": row.get("stop_time"),
                    "start_time": row.get("start_time"),
                },
                "source_ref": f"{legacy_system}:data_resource:{res_id}",
                "legacy_object_ref": res_id,
                "summary_json": {
                    "res_desc": row.get("res_desc"),
                    "res_version": row.get("res_version"),
                    "system_id": row.get("system_id"),
                    "apply_count": row.get("apply_count"),
                    "browse_count": row.get("browse_count"),
                    "stop_desc": row.get("stop_desc"),
                    "del_desc": row.get("del_desc"),
                    "historyversion": row.get("historyversion"),
                    "creator_name": row.get("creator_name"),
                    "file_store_type": row.get("file_store_type"),
                },
            },
            tenant_id=self.tenant_id,
        )

    def _map_rc_resource(self, row: dict[str, Any], legacy_system: str) -> None:
        resource_id = row["id"]
        resource_code = resource_id
        lifecycle = RESOURCE_STATUS_TO_LIFECYCLE.get(coerce_int(row.get("status")), "draft")
        resource_kind = _normalize_resource_kind(row.get("res_type"))
        self.resource_repo.upsert_asset(
            {
                "resource_code": resource_code,
                "resource_kind": resource_kind,
                "title": row.get("res_name") or resource_code,
                "lifecycle_status": lifecycle,
                "owner_org_id": row.get("org_id"),
                "owner_org_snapshot_json": {
                    "org_id": row.get("org_id"),
                    "org_name": row.get("org_name"),
                },
                "region_code": row.get("region_code"),
                "catalog_code": row.get("cata_id"),
                "access_policy_json": {
                    "share_type": row.get("share_type"),
                    "share_condition": row.get("share_condition"),
                    "open_type": row.get("open_type"),
                    "open_condition": row.get("open_condition"),
                    "inner_share_type": row.get("inner_share_type"),
                    "inner_share_condition": row.get("inner_share_condition"),
                    "authz_type": row.get("authz_type"),
                },
                "qos_policy_json": {
                    "update_cycle": row.get("update_cycle"),
                    "custom_update_cycle": row.get("custom_update_cycle"),
                    "publish_time": coerce_time(row.get("publish_time")),
                    "expire_time": coerce_time(row.get("expire_time")),
                    "create_time": coerce_time(row.get("create_time")),
                    "warn_status": row.get("warn_status"),
                    "data_update_overtime": row.get("data_update_overtime"),
                },
                "source_ref": f"{legacy_system}:rc_resource:{resource_id}",
                "legacy_object_ref": resource_id,
                "summary_json": {
                    "res_desc": row.get("res_desc"),
                    "version": row.get("version"),
                    "cata_name": row.get("cata_name"),
                    "from_system_id": row.get("from_system_id"),
                    "from_system_name": row.get("from_system_name"),
                    "from_cascade": row.get("from_cascade"),
                    "table_data_num": row.get("table_data_num"),
                    "create_method": row.get("create_method"),
                    "creator_name": row.get("creator_name"),
                    "is_saved_to_platform": row.get("is_saved_to_platform"),
                },
            },
            tenant_id=self.tenant_id,
        )


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _normalize_resource_kind(raw: Any) -> str:
    if not raw:
        return "table"
    text = str(raw).strip().lower()
    if text in {"table", "file", "folder", "service", "api", "url"}:
        return "service" if text == "service" else text
    return "table"
