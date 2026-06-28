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

from sqlalchemy import select

from zw_brain.adapters.legacy._common import (
    ImportStats,
    coerce_datetime,
    coerce_int,
    coerce_time,
    finish_run,
    schema_from_dump_name,
)
from zw_brain.adapters.legacy.clean_filter import SkipUnclean, is_clean_record
from zw_brain.adapters.legacy.parser import MysqldumpParser
from zw_brain.adapters.legacy.tenant_normalizer import DEFAULT_TENANT, legacy_system_for
from zw_brain.domain.models import (
    ApprovalCaseRecord,
    ApprovalDecisionRecord,
    ApprovalStepRecord,
    TopicPackageItemRecord,
    TopicPackageRecord,
    TopicPackageVisibilityRecord,
)
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.domain.repositories.delivery import DeliveryRepository
from zw_brain.domain.repositories.external_adapter import ExternalAdapterRepository
from zw_brain.domain.repositories.legacy_mapping import LegacyObjectMappingRepository, upsert_legacy_mapping_in_session
from zw_brain.domain.repositories.metadata_evidence import MetadataEvidenceRepository
from zw_brain.domain.repositories.resource_api import ResourceApiRepository
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.sanitization import safe_json

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
    HANDLED_TABLES = {
        "data_catalog",
        "data_catalog_column",
        "data_catalog_group",
        "data_group_permission",
        "data_basic_elem_catalog",
        "data_basic_elem_catalog_item",
        "data_resource",
        "rc_resource",
        "rc_resource_table",
        "rc_resource_file",
        "rc_resource_url",
        "rc_resource_api",
        "rc_resource_catalog_item_link",
        "db_meta_table",
        "db_meta_column",
        "meta_baseinfo",
        "meta_baseinfo_history",
        "meta_table_column",
        "meta_gather_task",
        "meta_relation",
        "rc_catalog_materialize",
        "resource_flow_log",
        "catalog_quality_task",
        "catalog_quality_result",
    }
    ADAPTER_SLUG = "legacy.catalog_metadata.import"

    def __init__(self, *, tenant_id: str = DEFAULT_TENANT, only_clean: bool = False):
        self.tenant_id = tenant_id
        self.only_clean = only_clean
        self.catalog_repo = CatalogRepository()
        self.resource_repo = ResourceApiRepository()
        self.metadata_repo = MetadataEvidenceRepository()
        self.delivery_repo = DeliveryRepository()
        self.adapter_repo = ExternalAdapterRepository()
        self.legacy_mapping_repo = LegacyObjectMappingRepository()

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
                elif table == "data_catalog_group":
                    self._map_data_catalog_group(row, legacy_system)
                elif table == "data_group_permission":
                    self._map_data_group_permission(row, legacy_system)
                elif table == "data_basic_elem_catalog":
                    self._map_data_basic_elem_catalog(row, legacy_system)
                elif table == "data_basic_elem_catalog_item":
                    self._map_data_basic_elem_catalog_item(row, legacy_system)
                elif table == "data_resource":
                    self._map_data_resource(row, legacy_system)
                elif table == "rc_resource":
                    self._map_rc_resource(row, legacy_system)
                elif table in {"rc_resource_table", "rc_resource_file", "rc_resource_url", "rc_resource_api"}:
                    self._map_resource_channel_binding(table, row, legacy_system)
                elif table == "rc_resource_catalog_item_link":
                    self._map_resource_catalog_item_link(row, legacy_system)
                elif table in {"db_meta_table", "db_meta_column", "meta_baseinfo", "meta_baseinfo_history", "meta_table_column"}:
                    self._map_schema_snapshot(table, row, legacy_system)
                elif table == "meta_gather_task":
                    self._map_gather_task(row, legacy_system)
                elif table == "meta_relation":
                    self._map_lineage_relation(row, legacy_system)
                elif table == "rc_catalog_materialize":
                    self._map_catalog_materialize(row, legacy_system)
                elif table == "resource_flow_log":
                    self._map_resource_flow_log(row, legacy_system)
                elif table in {"catalog_quality_task", "catalog_quality_result"}:
                    self._map_quality_evidence(table, row, legacy_system)
                stats.bump(table)
            except SkipUnclean as exc:
                # --only-clean：不达标业务记录跳过且记账（可审计，非静默）。
                stats.skip(f"{table}.unclean:{exc.reason}")
            except KeyError as exc:
                stats.bump(table, "errors")
                stats.skipped[f"{table}.missing_field:{exc.args[0]}"] = stats.skipped.get(f"{table}.missing_field:{exc.args[0]}", 0) + 1

        finish_run(self.adapter_repo, stats, adapter_slug=self.ADAPTER_SLUG, dump_path=dump_path, started_at=started_at, tenant_id=self.tenant_id)
        return stats

    # ------------------------------------------------------------------
    # per-table handlers
    # ------------------------------------------------------------------

    def _catalog_code_for(self, legacy_catalog_ref: Any, legacy_system: str) -> str | None:
        if legacy_catalog_ref is None or legacy_catalog_ref == "":
            return None
        text = str(legacy_catalog_ref)
        return (
            self.legacy_mapping_repo.resolve_canonical_ref(
                legacy_system=legacy_system,
                legacy_object_type="data_catalog",
                legacy_object_ref=text,
                canonical_type="catalog_entry",
                tenant_id=self.tenant_id,
            )
            or text
        )

    def _rebind_catalog_code(self, legacy_catalog_ref: Any, catalog_code: str) -> None:
        if legacy_catalog_ref is None or legacy_catalog_ref == "":
            return
        legacy_catalog_code = str(legacy_catalog_ref)
        self.catalog_repo.rebind_catalog_code(legacy_catalog_code, catalog_code, tenant_id=self.tenant_id)
        self.resource_repo.rebind_catalog_code(legacy_catalog_code, catalog_code, tenant_id=self.tenant_id)
        self.metadata_repo.rebind_catalog_code(legacy_catalog_code, catalog_code, tenant_id=self.tenant_id)

    def _map_data_catalog(self, row: dict[str, Any], legacy_system: str) -> None:
        cata_id = row["cata_id"]
        cata_code = row.get("cata_code") or cata_id
        catalog_code = str(cata_code)
        if self.only_clean:
            ok, reason = is_clean_record(
                "catalog",
                {"name": row.get("cata_title"), "id": catalog_code, "provider": row.get("org_code")},
            )
            if not ok:
                raise SkipUnclean(reason)
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
        self._attach_catalog_to_group_projection(row, catalog_code, legacy_system)
        self._rebind_catalog_code(cata_id, catalog_code)

    def _attach_catalog_to_group_projection(self, row: dict[str, Any], catalog_code: str, legacy_system: str) -> None:
        cata_id = row.get("cata_id")
        seen: set[str] = set()
        for group_id in (_first(row, "cata_group_id"), _first(row, "base_group_id"), _first(row, "theme_group_id")):
            if group_id is None or group_id == "" or str(group_id) in seen:
                continue
            seen.add(str(group_id))
            package_code = f"catalog-group:{group_id}"
            self._upsert_topic_package_projection(
                package_code=package_code,
                title=row.get("cata_group_name") or row.get("share_group_name") or f"目录分组 {group_id}",
                owner_org_id=row.get("org_code"),
                status="published" if CATALOG_STATUS_TO_LIFECYCLE.get(row.get("status")) == "active" else "configuring",
                display_snapshot_json={"projection_kind": "catalog_group", "source": "data_catalog", "group_id": group_id},
                source_ref=f"{legacy_system}:data_catalog:{cata_id}:group:{group_id}",
                replace_existing=False,
            )
            self._upsert_topic_item(
                package_code,
                {
                    "item_code": f"catalog:{catalog_code}",
                    "ref_type": "catalog_entry",
                    "ref_id": catalog_code,
                    "ref_status": CATALOG_STATUS_TO_LIFECYCLE.get(row.get("status"), "draft"),
                    "title": row.get("cata_title") or catalog_code,
                    "display_order": coerce_int(row.get("sort_level") or row.get("cata_order_code"), 0),
                    "summary_json": {"legacy_catalog_id": cata_id, "group_id": group_id, "source": "data_catalog"},
                },
            )

    def _map_data_catalog_column(self, row: dict[str, Any], legacy_system: str) -> None:
        cata_id = row["cata_id"]
        column_id = row["column_id"]
        catalog_code = self._catalog_code_for(cata_id, legacy_system) or str(cata_id)
        self.catalog_repo.upsert_item(
            {
                "item_code": column_id,
                "catalog_code": catalog_code,
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

    def _map_data_catalog_group(self, row: dict[str, Any], legacy_system: str) -> None:
        group_id = str(row["group_id"])
        package_code = f"catalog-group:{group_id}"
        self._upsert_topic_package_projection(
            package_code=package_code,
            title=row.get("group_name") or package_code,
            owner_org_id=None,
            status=_catalog_group_status(row.get("status")),
            display_snapshot_json={
                "projection_kind": "catalog_group",
                "group_code": row.get("group_code"),
                "group_name": row.get("group_name"),
                "parent_group_id": row.get("parent_group_id"),
                "order_id": row.get("order_id"),
                "is_del": row.get("is_del"),
                "source": "data_catalog_group",
            },
            source_ref=f"{legacy_system}:data_catalog_group:{group_id}",
            replace_existing=True,
        )
        self.legacy_mapping_repo.upsert_mapping(
            {
                "source_ref": f"{legacy_system}:data_catalog_group:{group_id}",
                "legacy_system": legacy_system,
                "legacy_object_type": "data_catalog_group",
                "legacy_object_ref": group_id,
                "canonical_type": "TopicPackageRecord",
                "canonical_ref": package_code,
                "evidence_json": {"group_name": row.get("group_name"), "projection_kind": "catalog_group"},
            },
            tenant_id=self.tenant_id,
        )

    def _map_data_group_permission(self, row: dict[str, Any], legacy_system: str) -> None:
        permission_id = str(row["id"])
        group_id = row.get("groupId")
        if group_id is None or group_id == "":
            return
        package_code = f"catalog-group:{group_id}"
        visibility = {
            "visibility_code": f"data_group_permission:{permission_id}",
            "org_code": row.get("userrsmid") if str(row.get("type") or "") != "role" else None,
            "role_code": row.get("userrsmid") if str(row.get("type") or "") == "role" else None,
            "surface": "webui",
            "intent": "view",
            "policy_status": "approved",
            "condition_json": {
                "legacy_permission_type": row.get("type"),
                "group_id": group_id,
                "group_code": row.get("groupCode"),
                "source": "data_group_permission",
            },
        }
        self._upsert_topic_package_projection(
            package_code=package_code,
            title=f"目录分组 {group_id}",
            owner_org_id=None,
            status="published",
            display_snapshot_json={"projection_kind": "catalog_group", "source": "data_group_permission", "group_id": group_id},
            source_ref=f"{legacy_system}:data_group_permission:{permission_id}",
            replace_existing=False,
        )
        self._upsert_topic_visibility(package_code, visibility)
        self.legacy_mapping_repo.upsert_mapping(
            {
                "source_ref": f"{legacy_system}:data_group_permission:{permission_id}",
                "legacy_system": legacy_system,
                "legacy_object_type": "data_group_permission",
                "legacy_object_ref": permission_id,
                "canonical_type": "TopicPackageVisibilityRecord",
                "canonical_ref": f"{package_code}:data_group_permission:{permission_id}",
                "evidence_json": {"package_code": package_code, "policy_status": "approved"},
            },
            tenant_id=self.tenant_id,
        )

    def _upsert_topic_package_projection(
        self,
        *,
        package_code: str,
        title: str,
        owner_org_id: str | None,
        status: str,
        display_snapshot_json: dict[str, Any],
        source_ref: str,
        replace_existing: bool,
    ) -> None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(
                select(TopicPackageRecord).where(
                    TopicPackageRecord.tenant_id == self.tenant_id,
                    TopicPackageRecord.package_code == package_code,
                )
            ).scalar_one_or_none()
            values = {
                "tenant_id": self.tenant_id,
                "package_code": package_code,
                "title": title,
                "scenario": "共享目录可见性 projection",
                "owner_org_id": owner_org_id,
                "owner_org_snapshot_json": {},
                "status": status,
                "display_snapshot_json": safe_json(display_snapshot_json),
                "metric_snapshot_json": {},
                "source_ref": source_ref,
            }
            if record is None:
                session.add(TopicPackageRecord(**values))
            elif replace_existing:
                for key, value in values.items():
                    setattr(record, key, value)
            session.commit()

    def _upsert_topic_item(self, package_code: str, item: dict[str, Any]) -> None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            item_code = str(item["item_code"])
            record = session.execute(
                select(TopicPackageItemRecord).where(
                    TopicPackageItemRecord.tenant_id == self.tenant_id,
                    TopicPackageItemRecord.package_code == package_code,
                    TopicPackageItemRecord.item_code == item_code,
                )
            ).scalar_one_or_none()
            values = {
                "tenant_id": self.tenant_id,
                "package_code": package_code,
                "item_code": item_code,
                "ref_type": str(item.get("ref_type", "catalog_entry")),
                "ref_id": str(item.get("ref_id", item_code)),
                "ref_status": str(item.get("ref_status", "active")),
                "title": str(item.get("title", item_code)),
                "display_order": int(item.get("display_order", 0)),
                "summary_json": safe_json(item.get("summary_json") or {}),
            }
            if record is None:
                session.add(TopicPackageItemRecord(**values))
            else:
                for key, value in values.items():
                    setattr(record, key, value)
            session.commit()

    def _upsert_topic_visibility(self, package_code: str, visibility: dict[str, Any]) -> None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            visibility_code = str(visibility["visibility_code"])
            record = session.execute(
                select(TopicPackageVisibilityRecord).where(
                    TopicPackageVisibilityRecord.tenant_id == self.tenant_id,
                    TopicPackageVisibilityRecord.package_code == package_code,
                    TopicPackageVisibilityRecord.visibility_code == visibility_code,
                )
            ).scalar_one_or_none()
            values = {
                "tenant_id": self.tenant_id,
                "package_code": package_code,
                "visibility_code": visibility_code,
                "org_code": visibility.get("org_code"),
                "role_code": visibility.get("role_code"),
                "region_code": visibility.get("region_code"),
                "surface": str(visibility.get("surface", "webui")),
                "intent": str(visibility.get("intent", "view")),
                "policy_status": str(visibility.get("policy_status", "approved")),
                "condition_json": safe_json(visibility.get("condition_json") or {}),
            }
            if record is None:
                session.add(TopicPackageVisibilityRecord(**values))
            else:
                for key, value in values.items():
                    setattr(record, key, value)
            session.commit()

    def _map_data_basic_elem_catalog(self, row: dict[str, Any], legacy_system: str) -> None:
        cata_id = str(row["cata_id"])
        catalog_code = f"basic-elem:{cata_id}"
        if self.only_clean:
            # 基础元素目录可无 provider（参考数据），仅按名称过滤测试/未命名（不要求机构，避免误伤）。
            ok, reason = is_clean_record("resource", {"name": row.get("cata_title"), "id": catalog_code})
            if not ok:
                raise SkipUnclean(reason)
        # `version` is part of legacy PK; first import wins as the basic_element catalog body.
        self.catalog_repo.upsert_from_resource(
            {
                "id": catalog_code,
                "name": row.get("cata_title") or catalog_code,
                "status": "active",
                "provider": row.get("imported_by_org_code"),
                "region_code": None,
                "source_ref": f"{legacy_system}:data_basic_elem_catalog:{cata_id}",
                "legacy_object_ref": cata_id,
                "summary": {
                    "kind": "basic_element",
                    "category_id": row.get("category_id"),
                    "category_code": row.get("category_code"),
                    "domain_id": row.get("domain_id"),
                    "level": row.get("level"),
                    "source_service_item_catalog_name": row.get("source_service_item_catalog_name"),
                    "source_service_item_catalog_code": row.get("source_service_item_catalog_code"),
                    "description": row.get("description"),
                    "business_line_code": row.get("business_line_code"),
                    "imported_by_org_code": row.get("imported_by_org_code"),
                    "imported_by_org_name": row.get("imported_by_org_name"),
                    "version": row.get("version"),
                    "create_time": coerce_time(row.get("create_time")),
                    "update_time": coerce_time(row.get("update_time")),
                },
            },
            tenant_id=self.tenant_id,
        )
        self._rebind_catalog_code(cata_id, catalog_code)

    def _map_data_basic_elem_catalog_item(self, row: dict[str, Any], legacy_system: str) -> None:
        cata_id = str(row["cata_id"])
        column_code = str(row["column_code"])
        cata_version = row.get("cata_version")
        catalog_code = (
            self.legacy_mapping_repo.resolve_canonical_ref(
                legacy_system=legacy_system,
                legacy_object_type="data_basic_elem_catalog",
                legacy_object_ref=cata_id,
                canonical_type="catalog_entry",
                tenant_id=self.tenant_id,
            )
            or f"basic-elem:{cata_id}"
        )
        # Item code combines column_code + cata_version to keep historical versions
        # addressable, since the legacy PK is (cata_id, cata_version, column_code).
        item_code = f"basic-elem:{cata_id}:{cata_version}:{column_code}"
        self.catalog_repo.upsert_item(
            {
                "item_code": item_code,
                "catalog_code": catalog_code,
                "title": row.get("name_cn") or column_code,
                "item_kind": "basic_element_field",
                "display_order": 0,
                "source_ref": f"{legacy_system}:data_basic_elem_catalog_item:{cata_id}:{cata_version}:{column_code}",
                "legacy_object_ref": f"{cata_id}:{cata_version}:{column_code}",
                "summary_json": {
                    "kind": "basic_element_field",
                    "data_format": row.get("data_format"),
                    "cata_version": cata_version,
                    "create_time": coerce_time(row.get("create_time")),
                },
            },
            tenant_id=self.tenant_id,
        )

    def _map_data_resource(self, row: dict[str, Any], legacy_system: str) -> None:
        res_id = row["res_id"]
        resource_code = str(row.get("res_code") or res_id)
        if self.only_clean:
            ok, reason = is_clean_record("resource", {"name": row.get("res_name"), "id": resource_code})
            if not ok:
                raise SkipUnclean(reason)
        lifecycle = RESOURCE_STATUS_TO_LIFECYCLE.get(coerce_int(row.get("status")), "draft")
        resource_kind = _normalize_resource_kind(row.get("res_type"))
        catalog_code = self._catalog_code_for(row.get("cata_id"), legacy_system)
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
                "catalog_code": catalog_code,
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

    def _map_resource_channel_binding(self, table: str, row: dict[str, Any], legacy_system: str) -> None:
        resource_code = str(_first(row, "resource_id", "res_id", "rc_resource_id", "id"))
        legacy_id = _channel_legacy_id(table, row, resource_code)
        binding_code = _channel_binding_code(table, row, resource_code, legacy_id)
        source_ref = f"{legacy_system}:{table}:{legacy_id}"
        channel_kind = _channel_kind_for(table)
        self.resource_repo.upsert_binding(
            {
                "binding_code": binding_code,
                "resource_code": resource_code,
                "channel_kind": channel_kind,
                "route_ref": _route_ref_for_channel(table, row),
                "endpoint_ref": _endpoint_ref_for_channel(table, row),
                "schema_ref": _schema_ref_for_channel(table, row),
                "request_schema_json": {},
                "response_schema_json": {},
                "gateway_policy_json": _sanitized_ref(row, include=("exchange_type", "share_type", "open_type", "need_mask", "file_format", "file_store_type")),
                "lifecycle_status": _normalize_channel_status(_first(row, "resource_status", "open_status", default="active")),
                "source_ref": source_ref,
                "legacy_object_ref": legacy_id or binding_code,
            },
            tenant_id=self.tenant_id,
        )

    def _map_resource_catalog_item_link(self, row: dict[str, Any], legacy_system: str) -> None:
        link_id = _first(row, "id", "link_id", "relation_id")
        catalog_item_raw = _first(row, "catalog_item_id", "item_id", "column_id")
        if catalog_item_raw is None or str(catalog_item_raw).strip() == "":
            # Real customer dumps include rows with empty catalog_item_id (legacy
            # placeholders); they would otherwise collapse onto the same
            # uq_resource_schema_mapping_current row with catalog_item_code='None'.
            return
        catalog_item_code = str(catalog_item_raw)
        resource_code = str(_first(row, "resource_id", "res_id", "rc_resource_id"))
        binding_code = str(_first(row, "binding_id", "table_id", default=resource_code))
        catalog_code = self._catalog_code_for(_first(row, "catalog_id", "cata_id"), legacy_system) or "unknown"
        source_column = _first(row, "table_column_id", "column_id", "field_name", "column_name")
        mapping_code = str(_first(row, "mapping_code", "id", default=f"{catalog_item_code}:{resource_code}:{binding_code}"))
        # Guard the (tenant_id, catalog_item_code, resource_code, binding_code, status)
        # unique constraint when legacy data has multiple link rows for the same triple:
        # if an active row already exists with a *different* mapping_code, demote the new
        # one to status='superseded' and disambiguate the binding so the UNIQUE still
        # holds for the (..., status='superseded') projection.
        status = "active"
        if self._has_active_mapping_for(catalog_item_code, resource_code, binding_code, mapping_code):
            status = "superseded"
            binding_code = f"{binding_code}#{mapping_code}"
        self.metadata_repo.upsert_schema_mapping(
            {
                "mapping_code": mapping_code,
                "catalog_code": catalog_code,
                "catalog_item_code": catalog_item_code,
                "resource_code": resource_code,
                "binding_code": binding_code,
                "source_schema_ref": {"column": row.get("table_column_name") or source_column, "table_column_id": row.get("table_column_id")},
                "mapping_rule_json": _sanitized_ref(row, include=("mapping_rule", "convert_rule", "desensitize_rule", "status")),
                "confidence_level": "confirmed",
                "evidence_ref": f"{legacy_system}:rc_resource_catalog_item_link:{link_id or catalog_item_code}",
                "source_ref": f"{legacy_system}:rc_resource_catalog_item_link:{link_id or catalog_item_code}",
                "legacy_object_ref": link_id or f"{catalog_item_code}:{resource_code}:{binding_code}",
                "status": status,
            },
            tenant_id=self.tenant_id,
        )

    def _has_active_mapping_for(
        self,
        catalog_item_code: str,
        resource_code: str,
        binding_code: str,
        mapping_code: str,
    ) -> bool:
        from sqlalchemy import select

        from zw_brain.domain.models import ResourceSchemaMappingRecord
        from zw_brain.shared.db import create_session_factory

        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            existing = session.execute(
                select(ResourceSchemaMappingRecord).where(
                    ResourceSchemaMappingRecord.tenant_id == self.tenant_id,
                    ResourceSchemaMappingRecord.catalog_item_code == catalog_item_code,
                    ResourceSchemaMappingRecord.resource_code == resource_code,
                    ResourceSchemaMappingRecord.binding_code == binding_code,
                    ResourceSchemaMappingRecord.status == "active",
                )
            ).scalar_one_or_none()
        if existing is None:
            return False
        # Same row re-import (idempotent apply) should keep active status.
        return existing.mapping_code != mapping_code

    def _map_schema_snapshot(self, table: str, row: dict[str, Any], legacy_system: str) -> None:
        meta_id = str(_first(row, "meta_id", "id", "column_id", "field_id"))
        if table == "db_meta_column":
            resource_code = str(_first(row, "table_meta_id", "meta_id", default=meta_id))
            binding_code = str(_first(row, "table_meta_id", default=resource_code))
            snapshot_ref = f"{resource_code}:db_meta_column:{meta_id}"
            schema_json = _sanitized_ref(
                row,
                include=(
                    "meta_id",
                    "table_meta_id",
                    "column_name",
                    "comment",
                    "remark",
                    "format",
                    "length",
                    "is_pk",
                    "is_null",
                    "meta_standard",
                    "meta_standard_cn",
                    "sensitive_level",
                    "order_id",
                    "need_encrypt",
                    "column_precision",
                ),
            )
        elif table == "db_meta_table":
            resource_code = str(_first(row, "meta_id", default=meta_id))
            binding_code = str(_first(row, "meta_id", default=resource_code))
            snapshot_ref = f"{resource_code}:db_meta_table:{meta_id}"
            schema_json = _sanitized_ref(
                row, include=("meta_id", "database_meta_id", "table_name", "comment", "unique_code", "remark", "update_cycle", "sensitive_level", "data_count", "recommend_status")
            )
        else:
            resource_code = str(_first(row, "resource_id", "res_id", "rc_resource_id", "meta_id", default=meta_id))
            binding_code = _first(row, "binding_id", "table_id", "area_id")
            snapshot_ref = f"{resource_code}:{table}:{meta_id}"
            schema_json = _sanitized_ref(
                row,
                include=(
                    "meta_id",
                    "meta_name",
                    "model_id",
                    "version",
                    "table_name",
                    "column_name",
                    "name_cn",
                    "name_en",
                    "data_type",
                    "data_format",
                    "length",
                    "comment",
                    "org_code",
                    "org_name",
                    "region_code",
                    "region_name",
                    "gather_type",
                    "status",
                ),
            )
        self.metadata_repo.upsert_schema_snapshot(
            {
                "snapshot_ref": snapshot_ref,
                "resource_code": resource_code,
                "binding_code": binding_code,
                "schema_json": schema_json,
                "source_ref": f"{legacy_system}:{table}:{meta_id}",
                "legacy_object_ref": meta_id,
                "captured_at": coerce_datetime(_first(row, "gather_time", "update_time", "create_time")),
            },
            tenant_id=self.tenant_id,
        )

    def _map_gather_task(self, row: dict[str, Any], legacy_system: str) -> None:
        task_ref = str(_first(row, "task_id", "job_id", "id"))
        resource_code = str(_first(row, "resource_id", "res_id", "meta_id", default=task_ref))
        self.metadata_repo.upsert_gather_evidence(
            {
                "gather_task_ref": task_ref,
                "resource_code": resource_code,
                "source_system_ref": _first(row, "datasource_id", "source_system_ref", "system_id"),
                "schema_snapshot_ref": _first(row, "schema_snapshot_ref", "meta_id"),
                "status": _normalize_gather_status(_first(row, "status", "task_status")),
                "error_summary": _first(row, "error_summary", "error_msg", "fail_reason"),
                "evidence_json": _sanitized_ref(row, include=("task_id", "job_id", "cron_exp", "status", "task_status")),
                "started_at": coerce_datetime(_first(row, "started_at", "start_time", "create_time")),
                "finished_at": coerce_datetime(_first(row, "finished_at", "end_time", "finish_time")),
                "source_ref": f"{legacy_system}:meta_gather_task:{task_ref}",
                "legacy_object_ref": task_ref,
            },
            tenant_id=self.tenant_id,
        )

    def _map_lineage_relation(self, row: dict[str, Any], legacy_system: str) -> None:
        relation_ref = str(_first(row, "relation_id", "id", default=f"{_first(row, 'source_meta_id')}:{_first(row, 'target_meta_id')}"))
        self.metadata_repo.upsert_lineage_relation(
            {
                "relation_ref": relation_ref,
                "relation_scope": str(_first(row, "relation_scope", default="table")),
                "source_resource_code": _first(row, "source_resource_id", "source_res_id", "source_meta_id"),
                "source_schema_ref": _first(row, "source_schema_ref", "source_column_id"),
                "target_resource_code": _first(row, "target_resource_id", "target_res_id", "target_meta_id"),
                "target_schema_ref": _first(row, "target_schema_ref", "target_column_id"),
                "relation_type": str(_first(row, "relation_type", "relation_from", default="imported")),
                "relation_rule_json": _sanitized_ref(row, include=("relation_from", "relation_type", "transform_rule", "remark")),
                "source_evidence_ref": f"{legacy_system}:meta_relation:{relation_ref}",
                "source_ref": f"{legacy_system}:meta_relation:{relation_ref}",
                "legacy_object_ref": relation_ref,
            },
            tenant_id=self.tenant_id,
        )

    def _map_catalog_materialize(self, row: dict[str, Any], legacy_system: str) -> None:
        cata_id = str(row["cata_id"])
        res_id = str(row.get("res_id") or cata_id)
        attempt_code = f"materialize:{cata_id}:{res_id}"
        self.delivery_repo.upsert_attempt(
            {
                "attempt_code": attempt_code,
                "delivery_code": f"materialize:{cata_id}",
                "attempt_kind": "catalog_materialize",
                "state": "recorded",
                "executor_ref": "external_materialize_executor",
                "evidence_ref": attempt_code,
                "payload_json": _sanitized_ref(row, include=("cata_id", "res_id", "table_name", "db_type")),
            },
            tenant_id=self.tenant_id,
        )
        self.delivery_repo.add_execution_evidence(
            {
                "evidence_ref": attempt_code,
                "delivery_code": f"materialize:{cata_id}",
                "attempt_code": attempt_code,
                "executor_kind": "external_materialize_executor",
                "executor_ref": "legacy.rc_catalog_materialize",
                "evidence_kind": "materialize_receipt",
                "result_status": "recorded",
                "payload_json": _sanitized_ref(row, include=("cata_id", "res_id", "table_name", "db_type")),
            },
            tenant_id=self.tenant_id,
        )
        self.legacy_mapping_repo.upsert_mapping(
            {
                "source_ref": f"{legacy_system}:rc_catalog_materialize:{cata_id}:{res_id}",
                "legacy_system": legacy_system,
                "legacy_object_type": "rc_catalog_materialize",
                "legacy_object_ref": f"{cata_id}:{res_id}",
                "canonical_type": "DeliveryAttemptRecord",
                "canonical_ref": attempt_code,
                "evidence_json": {"delivery_code": f"materialize:{cata_id}", "executor": "external_materialize_executor"},
            },
            tenant_id=self.tenant_id,
        )

    def _map_resource_flow_log(self, row: dict[str, Any], legacy_system: str) -> None:
        flow_id = str(row["id"])
        resource_id = str(row.get("resource_id") or flow_id)
        case_application_code = f"resource-review:{resource_id}"
        step_name = str(row.get("node_name") or row.get("node_code") or flow_id)
        decision = _resource_flow_decision(row.get("check_status"))
        step_status = "completed" if row.get("check_time") else "pending"
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            case = session.execute(
                select(ApprovalCaseRecord).where(
                    ApprovalCaseRecord.tenant_id == self.tenant_id,
                    ApprovalCaseRecord.application_code == case_application_code,
                )
            ).scalar_one_or_none()
            if case is None:
                case = ApprovalCaseRecord(
                    tenant_id=self.tenant_id,
                    application_code=case_application_code,
                    current_status=decision if step_status == "completed" else "pending_decision",
                    current_step=0,
                    decision_payload_json={"source": f"{legacy_system}:resource_flow_log", "resource_id": resource_id},
                )
                session.add(case)
                session.flush()
            else:
                case.current_status = decision if step_status == "completed" else "pending_decision"
            step = session.execute(
                select(ApprovalStepRecord).where(
                    ApprovalStepRecord.approval_case_id == case.id,
                    ApprovalStepRecord.step_name == step_name,
                )
            ).scalar_one_or_none()
            step_no = step.step_no if step is not None else (case.current_step or 0) + 1
            case.current_step = step_no
            step_payload = {
                "approval_case_id": case.id,
                "step_no": step_no,
                "step_name": step_name,
                "decision_mode": "single",
                "status": step_status,
                "approver_scope_json": safe_json(
                    {
                        "check_user_id": row.get("check_user_id"),
                        "check_user_name": row.get("check_user_name"),
                        "node_code": row.get("node_code"),
                        "node_name": row.get("node_name"),
                        "actor_code": row.get("actor_code"),
                        "flow_code": row.get("flow_code"),
                    }
                ),
                "started_at": coerce_datetime(row.get("check_time")),
                "completed_at": coerce_datetime(row.get("check_time")) if step_status == "completed" else None,
            }
            if step is None:
                step = ApprovalStepRecord(**step_payload)
                session.add(step)
                session.flush()
            else:
                for key, value in step_payload.items():
                    setattr(step, key, value)
            decision_record = None
            if step_status == "completed":
                decision_record = session.execute(select(ApprovalDecisionRecord).where(ApprovalDecisionRecord.step_id == step.id)).scalar_one_or_none()
                decision_payload = {
                    "step_id": step.id,
                    "decision": decision,
                    "decision_reason": row.get("check_note"),
                    "actor_snapshot_json": safe_json({"check_user_id": row.get("check_user_id"), "check_user_name": row.get("check_user_name")}),
                    "evidence_json": safe_json({"flow_id": flow_id, "resource_id": resource_id, "check_type": row.get("check_type"), "last_node": row.get("last_node")}),
                }
                if decision_record is None:
                    decision_record = ApprovalDecisionRecord(**decision_payload)
                    session.add(decision_record)
                    session.flush()
                else:
                    for key, value in decision_payload.items():
                        setattr(decision_record, key, value)
            steps_for_case = list(session.execute(select(ApprovalStepRecord).where(ApprovalStepRecord.approval_case_id == case.id)).scalars())
            ordered_steps = sorted(steps_for_case, key=lambda item: ((item.started_at or item.completed_at or item.created_at).isoformat(), item.step_name))
            for index, case_step in enumerate(ordered_steps, start=1):
                case_step.step_no = index
            case.current_step = len(ordered_steps)
            upsert_legacy_mapping_in_session(
                session,
                {
                    "source_ref": f"{legacy_system}:resource_flow_log:{flow_id}",
                    "legacy_object_ref": flow_id,
                    "canonical_type": "approval_step",
                    "canonical_ref": step.id,
                    "evidence_json": {"application_code": case_application_code, "resource_id": resource_id, "decision": decision},
                },
                tenant_id=self.tenant_id,
            )
            if decision_record is not None:
                upsert_legacy_mapping_in_session(
                    session,
                    {
                        "source_ref": f"{legacy_system}:resource_flow_log:{flow_id}",
                        "legacy_object_ref": flow_id,
                        "canonical_type": "approval_decision",
                        "canonical_ref": decision_record.id,
                        "evidence_json": {"application_code": case_application_code, "resource_id": resource_id, "decision": decision},
                    },
                    tenant_id=self.tenant_id,
                )
            session.commit()

    def _map_quality_evidence(self, table: str, row: dict[str, Any], legacy_system: str) -> None:
        quality_ref = str(_first(row, "quality_id", "task_id", "result_id", "id"))
        self.metadata_repo.upsert_quality_evidence(
            {
                "quality_ref": f"{table}:{quality_ref}",
                "target_type": str(_first(row, "target_type", default="catalog")),
                "target_ref": str(_first(row, "target_ref", "cata_id", "resource_id", "res_id", default=quality_ref)),
                "quality_status": _normalize_quality_status(_first(row, "quality_status", "status", "result")),
                "score": coerce_int(_first(row, "score", "quality_score"), 0) if _first(row, "score", "quality_score") is not None else None,
                "evidence_json": _sanitized_ref(row, include=("rule_code", "rule_name", "status", "result", "score", "quality_score", "summary")),
                "source_ref": f"{legacy_system}:{table}:{quality_ref}",
                "legacy_object_ref": quality_ref,
            },
            tenant_id=self.tenant_id,
        )

    def _map_rc_resource(self, row: dict[str, Any], legacy_system: str) -> None:
        resource_id = row["id"]
        resource_code = resource_id
        lifecycle = RESOURCE_STATUS_TO_LIFECYCLE.get(coerce_int(row.get("status")), "draft")
        resource_kind = _normalize_resource_kind(row.get("res_type"))
        catalog_code = self._catalog_code_for(row.get("cata_id"), legacy_system)
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
                "catalog_code": catalog_code,
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


def _channel_legacy_id(table: str, row: dict[str, Any], resource_code: str) -> str:
    if table.endswith("url"):
        return f"{resource_code}:url"
    return str(_first(row, "id", "table_id", "api_id", "resource_id", "res_id", default=resource_code))


def _channel_binding_code(table: str, row: dict[str, Any], resource_code: str, legacy_id: str) -> str:
    if table.endswith("url"):
        return f"{resource_code}:url"
    return str(_first(row, "binding_code", "table_id", "api_id", "id", default=legacy_id or f"binding:{resource_code}"))


def _catalog_group_status(raw: Any) -> str:
    text = str(raw if raw is not None else "1")
    if text == "1":
        return "published"
    if text == "0":
        return "offline"
    return "draft"


def _channel_kind_for(table: str) -> str:
    if table.endswith("api"):
        return "api_gateway"
    if table.endswith("file"):
        return "file"
    if table.endswith("url"):
        return "url"
    return "table"


def _route_ref_for_channel(table: str, row: dict[str, Any]) -> Any:
    if table.endswith("file"):
        return _first(row, "file_name", "file_format")
    if table.endswith("url"):
        return _first(row, "url_name", "url_code")
    return _first(row, "table_name", "api_path", "path", "route_ref")


def _endpoint_ref_for_channel(table: str, row: dict[str, Any]) -> dict[str, Any]:
    if table.endswith("file"):
        return _sanitized_ref(row, include=("file_name", "file_format", "file_source", "file_store_type", "node_id", "node_name", "exchange_en", "exchange_name"))
    if table.endswith("url"):
        return _sanitized_ref(row, include=("url_name", "url_code", "url_description"))
    return _sanitized_ref(row, include=("datasource_id", "database_id", "table_id", "api_id", "schema_name", "table_name", "api_path"))


def _schema_ref_for_channel(table: str, row: dict[str, Any]) -> dict[str, Any]:
    if table.endswith("file"):
        return _sanitized_ref(row, include=("file_name", "file_format", "file_size", "data_count"))
    if table.endswith("url"):
        return _sanitized_ref(row, include=("url_name", "url_code"))
    return _sanitized_ref(row, include=("table_id", "table_name", "schema_name", "version", "table_version"))


def _normalize_channel_status(raw: Any) -> str:
    text = str(raw or "active").strip().lower()
    if text in {"0", "active", "enabled", "published"}:
        return "active"
    if text in {"1", "draft"}:
        return "draft"
    if text in {"2", "pending", "pending_review"}:
        return "pending_review"
    if text in {"-1", "deleted"}:
        return "deleted"
    return "active"


def _resource_flow_decision(raw: Any) -> str:
    text = str(raw if raw is not None else "1").strip().lower()
    if text in {"1", "approved", "pass", "passed"}:
        return "approved"
    if text in {"2", "rejected", "reject"}:
        return "rejected"
    if text in {"0", "correction", "request_correction"}:
        return "request_correction"
    return "approved"


def _normalize_resource_kind(raw: Any) -> str:
    # 资源类型收敛为「库表 / 文件 / API」（D53）——唯一入库闸门。
    # 文件夹/链接退役：folder/url/link 折叠归并为 file（文件夹按文件处理；链接真实数据近零）。
    # service = 旧融合/代理服务，属 API 范畴的历史别名，保留。
    if not raw:
        return "table"
    text = str(raw).strip().lower()
    if text in {"table", "file", "api", "service"}:
        return text
    if text in {"folder", "url", "link"}:
        return "file"
    return "table"


def _first(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and value != "":
            return value
    return default


def _sanitized_ref(row: dict[str, Any], *, include: tuple[str, ...]) -> dict[str, Any]:
    return {key: row[key] for key in include if row.get(key) is not None and row.get(key) != ""}


def _normalize_gather_status(raw: Any) -> str:
    text = str(raw or "pending").strip().lower()
    if text in {"1", "success", "succeeded", "done", "finished"}:
        return "succeeded"
    if text in {"2", "failed", "fail", "error"}:
        return "failed"
    if text in {"running", "processing"}:
        return "running"
    if text in {"stale", "expired"}:
        return "stale"
    return "pending"


def _normalize_quality_status(raw: Any) -> str:
    text = str(raw or "unknown").strip().lower()
    if text in {"1", "pass", "passed", "ok", "succeeded"}:
        return "passed"
    if text in {"0", "fail", "failed", "error"}:
        return "failed"
    if text in {"warning", "warn"}:
        return "warning"
    return "unknown"
