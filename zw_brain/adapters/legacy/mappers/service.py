"""dsp_service → ResourceAsset(kind=api) + ResourceChannelBinding + invocation metrics.

Steps in the bridging chain after catalog/exchange. Each `api_service_info` row
becomes a ResourceAssetRecord with resource_kind="api". The data/proxy/general
companion tables attach as ResourceChannelBindingRecord rows. Consumer applications
(`api_service_app`) become ExternalObjectMappingRecord entries with their secrets
stripped at the row boundary. Per-day/per-app invocation metrics
(`api_service_times`) collapse into ServiceInvocationMetricProjectionRecord.

Real-secret fields dropped at row boundary: SECRET, superior_app_secret on
api_service_app; api_check_info CONTENT may carry sensitive review notes — kept in
audit evidence path under the legacy_object_mapping evidence_json (which is itself
sanitized via safe_json before persisting).
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
from zw_brain.domain.repositories.legacy_mapping import LegacyObjectMappingRepository
from zw_brain.domain.repositories.resource_api import ResourceApiRepository
from zw_brain.domain.repositories.service_invocation import ServiceInvocationMetricRepository

# Real secrets — never enter canonical / projection state.
APP_DROP_FIELDS = {"SECRET", "superior_app_secret", "superior_app_key"}


class ServiceMapper:
    HANDLED_TABLES = {
        "api_service_info",
        "api_service_data",
        "api_service_proxy",
        "api_service_general",
        "api_group",
        "api_service_app",
        "api_service_times",
    }
    ADAPTER_SLUG = "legacy.dataservice.import"

    def __init__(self, *, tenant_id: str = DEFAULT_TENANT):
        self.tenant_id = tenant_id
        self.resource_repo = ResourceApiRepository()
        self.catalog_repo = CatalogRepository()
        self.adapter_repo = ExternalAdapterRepository()
        self.legacy_repo = LegacyObjectMappingRepository()
        self.metric_repo = ServiceInvocationMetricRepository()
        # Buffer api_service_general rows so we can merge into the matching asset
        # once both tables have flowed past (general is keyed on SERVICE_ID).
        self._general_by_service: dict[str, dict[str, Any]] = {}

    def import_dump(self, dump_path: Path) -> ImportStats:
        schema = schema_from_dump_name(dump_path.name)
        legacy_system = legacy_system_for(schema)
        stats = ImportStats(schema=schema, dump_path=dump_path)
        started_at = datetime.now(UTC)

        # Single pass: buffer api_service_info rows so we can merge in any
        # api_service_general row that arrives later (parser yields rows in dump
        # order — both tables are at the top of the dump, but api_service_general
        # may appear before or after api_service_info depending on dump version).
        # All other tables map immediately.
        info_rows: list[dict[str, Any]] = []

        for table, row in MysqldumpParser(dump_path).iter_rows():
            if table not in self.HANDLED_TABLES:
                stats.skip(table)
                continue
            try:
                if table == "api_service_info":
                    info_rows.append(row)
                    continue  # bumped after merge below
                if table == "api_service_general":
                    self._general_by_service[row.get("SERVICE_ID") or row.get("API_ID") or ""] = row
                    continue  # not bumped — merged into info, see below
                if table == "api_service_data":
                    self._map_service_channel(row, legacy_system, channel_kind="data")
                elif table == "api_service_proxy":
                    self._map_service_channel(row, legacy_system, channel_kind="proxy")
                elif table == "api_group":
                    self._map_api_group(row, legacy_system)
                elif table == "api_service_app":
                    self._map_service_app(row, legacy_system)
                elif table == "api_service_times":
                    self._map_service_times(row, legacy_system)
                stats.bump(table)
            except KeyError as exc:
                stats.bump(table, "errors")
                key = f"{table}.missing_field:{exc.args[0]}"
                stats.skipped[key] = stats.skipped.get(key, 0) + 1

        # Apply buffered api_service_info rows now that all api_service_general
        # rows are cached.
        for row in info_rows:
            try:
                self._map_service_info(row, legacy_system)
                stats.bump("api_service_info")
            except KeyError as exc:
                stats.bump("api_service_info", "errors")
                key = f"api_service_info.missing_field:{exc.args[0]}"
                stats.skipped[key] = stats.skipped.get(key, 0) + 1

        if self._general_by_service:
            stats.counts["api_service_general.merged"] = len(self._general_by_service)

        finish_run(self.adapter_repo, stats, adapter_slug=self.ADAPTER_SLUG, dump_path=dump_path, started_at=started_at, tenant_id=self.tenant_id)
        return stats

    # ------------------------------------------------------------------

    def _map_service_info(self, row: dict[str, Any], legacy_system: str) -> None:
        service_id = row["ID"]
        general = self._general_by_service.get(service_id, {})
        is_public = str(row.get("IS_PUBLIC") or "0") == "1"
        audit_type = row.get("AUDIT_TYPE")
        self.resource_repo.upsert_asset(
            {
                "resource_code": service_id,
                "resource_kind": "api",
                "title": row.get("NAME") or service_id,
                "lifecycle_status": "active" if is_public else "draft",
                "owner_org_id": row.get("ORG_CODE"),
                "owner_org_snapshot_json": {
                    "org_code": row.get("ORG_CODE"),
                    "org_name": row.get("ORG_NAME"),
                    "region_code": row.get("REGION_CODE"),
                    "region_name": row.get("REGION_NAME"),
                },
                "region_code": row.get("REGION_CODE"),
                "access_policy_json": {
                    "is_public": is_public,
                    "audit_type": audit_type,
                    "use_model": row.get("USE_MODEL"),
                    "data_scope": row.get("data_scope"),
                    "business_scope": row.get("BUSINESS_SCOPE"),
                    "type": row.get("TYPE"),
                    "recommend": row.get("RECOMMEND"),
                },
                "qos_policy_json": {
                    "system_code": row.get("SYSTEM_CODE"),
                    "system_name": row.get("SYSTEM_NAME"),
                    "join_process": row.get("JOIN_PROCESS"),
                    "data_interaction": row.get("DATA_INTERACTION"),
                },
                "source_ref": f"{legacy_system}:api_service_info:{service_id}",
                "legacy_object_ref": service_id,
                "summary_json": {
                    "description": row.get("DESCRIPTION"),
                    "image_id": row.get("IMAGE_ID"),
                    "image_name": row.get("IMAGE_NAME"),
                    "creator": row.get("CREATOR"),
                    "join_process_org": row.get("JOIN_PROCESS_ORG"),
                    "item_code": row.get("ITEM_CODE"),
                    "item_name": row.get("ITEM_NAME"),
                    "advantage_list": general.get("ADVANTAGE_LIST"),
                    "scene_list": general.get("SCENE_LIST"),
                },
            },
            tenant_id=self.tenant_id,
        )

    def _map_service_channel(self, row: dict[str, Any], legacy_system: str, *, channel_kind: str) -> None:
        api_id = row["API_ID"]
        service_id = row.get("SERVICE_ID")
        # Channel binding code: "<service_id>:<channel_kind>:<api_id>" — keeps it stable
        # across re-runs and unique within (tenant, binding_code).
        binding_code = f"{service_id or 'standalone'}:{channel_kind}:{api_id}"
        if channel_kind == "data":
            endpoint_ref = {
                "table_name": row.get("TABLE_NAME"),
                "service_url": row.get("SERVICE_URL"),
                "datasource_id": row.get("DATASOURCE_ID"),
                "datalake_id": row.get("DATALAKE_ID"),
                "service_type": row.get("SERVICE_TYPE"),
                "page_flag": row.get("PAGE_FLAG"),
            }
            schema_ref = {
                "rule_param": row.get("RULE_PARAM"),
                "rule_str": row.get("RULE_STR"),
                "service_sql": row.get("SERVICE_SQL"),
            }
            gateway_policy: dict[str, Any] = {}
        else:  # proxy
            endpoint_ref = {
                "proxy_url": row.get("PROXY_URL"),
                "rest_method": row.get("REST_METHOD"),
                "call_type": row.get("CALL_TYPE"),
                "ws_soapaction": row.get("WS_SOAPACTION"),
                "ws_ns": row.get("WS_NS"),
                "ws_func": row.get("WS_FUNC"),
                "data_lake_service_name": row.get("data_lake_service_name"),
                "data_lake_service_id": row.get("data_lake_service_id"),
            }
            schema_ref = {}
            gateway_policy = {
                "frequency_time": row.get("FREQUENCY_TIME"),
                "frequency_num": row.get("FREQUENCY_NUM"),
                "cloud_grade": row.get("CLOUD_GRADE"),
                "header_back_flag": row.get("HEADER_BACK_FLAG"),
                "test_status": row.get("STATUS"),
            }
        self.resource_repo.upsert_binding(
            {
                "binding_code": binding_code,
                "resource_code": service_id or api_id,
                "channel_kind": channel_kind,
                "route_ref": row.get("PROXY_URL") or row.get("SERVICE_URL"),
                "endpoint_ref": endpoint_ref,
                "schema_ref": schema_ref,
                "gateway_policy_json": gateway_policy,
                "request_schema_json": {},
                "response_schema_json": {},
                "source_ref": f"{legacy_system}:api_service_{channel_kind}:{api_id}",
                "legacy_object_ref": api_id,
            },
            tenant_id=self.tenant_id,
        )

    def _map_api_group(self, row: dict[str, Any], legacy_system: str) -> None:
        # API group → CatalogEntry. We use a `api-group:` prefix on the catalog_code
        # so it doesn't collide with primary catalog_code namespace.
        group_id = row["group_id"]
        catalog_code = f"api-group:{row.get('group_code') or group_id}"
        self.catalog_repo.upsert_from_resource(
            {
                "id": catalog_code,
                "name": row.get("group_name") or group_id,
                "status": "active" if coerce_int(row.get("status"), 0) == 0 else "retired",
                "provider": "platform",
                "source_ref": f"{legacy_system}:api_group:{group_id}",
                "legacy_object_ref": group_id,
                "summary": {
                    "group_code": row.get("group_code"),
                    "parent_group_id": row.get("parent_group_id"),
                    "remark": row.get("remark"),
                    "order_id": row.get("order_id"),
                    "sequence_num": row.get("sequence_num"),
                    "kind": "api_group",
                },
            },
            tenant_id=self.tenant_id,
        )

    def _map_service_app(self, row: dict[str, Any], legacy_system: str) -> None:
        # Consumer application → external mapping (no secrets).
        scrubbed = {k: v for k, v in row.items() if k not in APP_DROP_FIELDS}
        app_link_id = scrubbed["ID"]
        self.legacy_repo.upsert_mapping(
            {
                "source_ref": f"{legacy_system}:api_service_app:{app_link_id}",
                "legacy_system": legacy_system,
                "legacy_object_type": "api_service_app",
                "legacy_object_ref": app_link_id,
                "canonical_type": "ExternalApplicationMapping",
                "canonical_ref": str(scrubbed.get("APP_ID") or app_link_id),
                "evidence_json": {
                    "service_id": scrubbed.get("SERVICE_ID"),
                    "app_id": scrubbed.get("APP_ID"),
                    "app_code": scrubbed.get("APP_CODE"),
                    "app_name": scrubbed.get("APP_NAME"),
                    "developer_id": scrubbed.get("DEVELOPER_ID"),
                    "auth_type": scrubbed.get("AUTH_TYPE"),
                    "frequency_time": scrubbed.get("FREQUENCY_TIME"),
                    "frequency_num": scrubbed.get("FREQUENCY_NUM"),
                    "life_time": scrubbed.get("LIFE_TIME"),
                    "secret_end_time": coerce_time(scrubbed.get("SECRET_END_TIME")),
                    "expire_time": scrubbed.get("EXPIRE_TIME"),
                    "call_times": scrubbed.get("call_times"),
                    "status": scrubbed.get("STATUS"),
                    "create_time": coerce_time(scrubbed.get("CREATE_TIME")),
                },
            },
            tenant_id=self.tenant_id,
        )

    def _map_service_times(self, row: dict[str, Any], legacy_system: str) -> None:
        api_id = row.get("api_id") or ""
        if not api_id:
            return
        date_int = coerce_int(row.get("date"), 0)
        time_bucket = (
            f"{date_int // 10000:04d}-{(date_int // 100) % 100:02d}-{date_int % 100:02d}"
            if date_int else f"{coerce_int(row.get('year'), 1970):04d}-{coerce_int(row.get('month'), 1):02d}-{coerce_int(row.get('day'), 1):02d}"
        )
        self.metric_repo.upsert_metric(
            {
                "metric_scope": "service",
                "resource_code": api_id,
                "capability_id": api_id,
                "provider_org_id": row.get("provider_org_code"),
                "consumer_org_id": row.get("caller_org_code"),
                "provider_region_code": row.get("provider_region_code"),
                "consumer_region_code": row.get("caller_region_code"),
                "consumer_app_ref": row.get("caller_app_id"),
                "bucket_granularity": "day",
                "time_bucket": time_bucket,
                "invoke_count": coerce_int(row.get("called_times"), 0),
                "success_count": coerce_int(row.get("called_success_times"), 0),
                "source_event_ref": f"{legacy_system}:api_service_times:{row.get('id')}",
                "summary_json": {
                    "api_name": row.get("api_name"),
                    "api_type": row.get("api_type"),
                    "caller_app_name": row.get("caller_app_name"),
                    "caller_app_key": row.get("caller_app_key"),
                    "data_lake_service_id": row.get("data_lake_service_id"),
                },
            },
            tenant_id=self.tenant_id,
        )
