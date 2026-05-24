"""dsp_basesubject → TopicPackageRecord mapper (F3 turn 2 漏做补齐).

Step 6 (basesubject branch) of the bridging chain. 主题库（basesubject = 行业级共享专题）的
主体实体（basesubject_info / basesubject_object_info / bs_resource / schema_info 等 11 表）
映射到 TopicPackageRecord 主线，让主题库与 dsp_example 共享专题在同一 canonical 模型下读。

dump 来源：`old/10示例数据/dump-dsp_basesubject-*.sql`（行业试点期；本地客户实际 dump 内
basesubject 主表 INSERT 为空，但 schema 已就位 → 准备好接收行业增量同步）

mapping 设计（11 表 → TopicPackageRecord + 子结构）:
  basesubject_info               → TopicPackageRecord（主题主体）
  basesubject_object_info        → display_snapshot_json.objects
  basesubject_object_resource_link → TopicPackageItemRecord（item / 对象-资源关联）
  basesubject_schema             → display_snapshot_json.schemas
  basesubject_schema_item_link   → display_snapshot_json.schemas[].items
  basesubject_service_info       → display_snapshot_json.services
  bs_resource                    → TopicPackageItemRecord（item / 主题库资源）
  bs_resource_column             → display_snapshot_json.resources[].columns
  bs_catalog_info                → display_snapshot_json.catalog_links
  schema_info                    → display_snapshot_json.schema_metas
  schema_resource                → display_snapshot_json.schema_metas[].resources

不复造表（基线 §1.3 forbidden zone）：population_* / corporation_* / archive_* /
data_schema_export / bs_subject_statistic / basesubject_job_* / webfinal_* —— 这些是统计
报表 + 数据治理任务运行细节，由集团数据治理中心统一。

Sensitive fields:
  - basesubject_info.contacter / contact_phone 是业务可见的联系信息，按 [2026-05-06] 策略
    保留原值进入 display_snapshot_json.contact，读层应用 sensitive_mask
  - 无真 secret 字段（无 password / token / hmac）
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
from zw_brain.domain.repositories.external_adapter import ExternalAdapterRepository
from zw_brain.domain.repositories.legacy_mapping import LegacyObjectMappingRepository
from zw_brain.domain.repositories.topic_package import TopicPackageRepository


class BasesubjectMapper:
    """Maps dsp_basesubject.* tables onto TopicPackage* records.

    一个 basesubject_info 行 → 一个 TopicPackageRecord，子表数据 join 进
    display_snapshot_json 与 items（resource link）。parser 按 dump 顺序 yield row，
    所以 mapper 先 buffer 全量行，再以 basesubject_info 为主体重组装。
    """

    HANDLED_TABLES = {
        "basesubject_info",
        "basesubject_object_info",
        "basesubject_object_resource_link",
        "basesubject_schema",
        "basesubject_schema_item_link",
        "basesubject_service_info",
        "bs_resource",
        "bs_resource_column",
        "bs_catalog_info",
        "schema_info",
        "schema_resource",
    }
    ADAPTER_SLUG = "legacy.basesubject.import"

    def __init__(self, *, tenant_id: str = DEFAULT_TENANT):
        self.tenant_id = tenant_id
        self.topic_repo = TopicPackageRepository()
        self.legacy_repo = LegacyObjectMappingRepository()
        self.adapter_repo = ExternalAdapterRepository()

    def import_dump(self, dump_path: Path) -> ImportStats:
        schema = schema_from_dump_name(dump_path.name)
        legacy_system = legacy_system_for(schema)
        stats = ImportStats(schema=schema, dump_path=dump_path)
        started_at = datetime.now(UTC)

        # Pass 1: buffer all rows by table
        buffers: dict[str, list[dict[str, Any]]] = {t: [] for t in self.HANDLED_TABLES}
        for table, row in MysqldumpParser(dump_path).iter_rows():
            if table not in self.HANDLED_TABLES:
                stats.skip(table)
                continue
            buffers[table].append(row)
            stats.bump_source(table)

        # Pass 2: index children by parent key
        objects_by_subject = _group_by(buffers["basesubject_object_info"], "basesubject_id")
        object_links_by_object = _group_by(buffers["basesubject_object_resource_link"], "basesubject_object_id")
        schemas_by_belongs = _group_by(buffers["basesubject_schema"], "belongs_id")
        schema_items_by_info_item = _group_by(buffers["basesubject_schema_item_link"], "info_item_id")
        services_by_subject = _group_by(buffers["basesubject_service_info"], "basesubject_id")
        bs_resources_by_subject = _group_by(buffers["bs_resource"], "basesubject_id")
        bs_resource_columns_by_resource = _group_by(buffers["bs_resource_column"], "resource_id")
        # bs_catalog_info 与 schema_info / schema_resource 是平级主题库元数据，按 org_code 索引
        catalogs_by_org = _group_by(buffers["bs_catalog_info"], "org_code")
        schema_metas_by_authority = _group_by(buffers["schema_info"], "authority_org_code")
        schema_resources_by_schema = _group_by(buffers["schema_resource"], "schema_id")

        # Pass 3: write one TopicPackage per basesubject_info row
        for subject in buffers["basesubject_info"]:
            try:
                self._import_one(
                    subject,
                    legacy_system=legacy_system,
                    objects=objects_by_subject.get(subject.get("id"), []),
                    object_links_index=object_links_by_object,
                    schemas=schemas_by_belongs.get(subject.get("id"), []),
                    schema_items_index=schema_items_by_info_item,
                    services=services_by_subject.get(subject.get("id"), []),
                    bs_resources=bs_resources_by_subject.get(subject.get("id"), []),
                    bs_resource_columns_index=bs_resource_columns_by_resource,
                    catalog_links=catalogs_by_org.get(subject.get("lead_org_code"), []),
                    schema_metas=schema_metas_by_authority.get(subject.get("lead_org_code"), []),
                    schema_resources_index=schema_resources_by_schema,
                )
                stats.bump("basesubject_info")
            except (KeyError, ValueError) as exc:
                stats.bump("basesubject_info", "errors")
                key = f"basesubject_info.error:{type(exc).__name__}"
                stats.skipped[key] = stats.skipped.get(key, 0) + 1

        # Bookkeeping: count child rows attached (for stats target view)
        for table in ("basesubject_object_info", "basesubject_object_resource_link",
                      "basesubject_schema", "basesubject_schema_item_link",
                      "basesubject_service_info", "bs_resource", "bs_resource_column",
                      "bs_catalog_info", "schema_info", "schema_resource"):
            count = len(buffers[table])
            if count:
                stats.counts[f"{table}.buffered"] = count

        finish_run(
            self.adapter_repo,
            stats,
            adapter_slug=self.ADAPTER_SLUG,
            dump_path=dump_path,
            started_at=started_at,
            tenant_id=self.tenant_id,
        )
        return stats

    # ------------------------------------------------------------------
    # one-subject pipeline
    # ------------------------------------------------------------------

    def _import_one(
        self,
        subject: dict[str, Any],
        *,
        legacy_system: str,
        objects: list[dict[str, Any]],
        object_links_index: dict[Any, list[dict[str, Any]]],
        schemas: list[dict[str, Any]],
        schema_items_index: dict[Any, list[dict[str, Any]]],
        services: list[dict[str, Any]],
        bs_resources: list[dict[str, Any]],
        bs_resource_columns_index: dict[Any, list[dict[str, Any]]],
        catalog_links: list[dict[str, Any]],
        schema_metas: list[dict[str, Any]],
        schema_resources_index: dict[Any, list[dict[str, Any]]],
    ) -> None:
        raw_id = subject.get("id")
        if raw_id is None or str(raw_id).strip() == "":
            # NULL id rows 否则会 collide 成 package_code="None" — fail-closed 而非 silent merge
            raise ValueError("basesubject_info row missing id; refuse silent collision")
        package_code = str(raw_id)
        title = subject.get("name") or package_code
        scenario = "主题库 / basesubject"

        # 子结构 join 进 display_snapshot_json — read 层可一次拿到
        objects_payload = [
            {
                "object_id": obj.get("id"),
                "object_name": obj.get("name"),
                "description": obj.get("description"),
                "resource_count": coerce_int(obj.get("resource_num")),
                "service_count": coerce_int(obj.get("service_num")),
                "status": obj.get("status"),
                "resources": [
                    {
                        "link_id": link.get("link_id"),
                        "resource_id": link.get("resource_id"),
                        "resource_type": link.get("resource_type"),
                        "status": link.get("status"),
                    }
                    for link in object_links_index.get(obj.get("id"), [])
                ],
            }
            for obj in objects
        ]

        schemas_payload = [
            {
                "schema_id": s.get("schema_id"),
                "schema_name": s.get("schema_name"),
                "relay_key": s.get("relay_key"),
                "relay_key_name": s.get("relay_key_name"),
                "create_org_code": s.get("create_org_code"),
                "items": [
                    {
                        "id": item.get("id"),
                        "info_item_id": item.get("info_item_id"),
                        "info_item_name": item.get("info_item_name"),
                        "source_info_item": item.get("source_info_item"),
                        "source_org_code": item.get("source_org_code"),
                        "source_org_name": item.get("source_org_name"),
                        "resource_id": item.get("resource_id"),
                    }
                    for item in schema_items_index.get(s.get("schema_id"), [])
                ],
            }
            for s in schemas
        ]

        services_payload = [
            {
                "service_id": s.get("service_id"),
                "service_name": s.get("service_name"),
                "type": s.get("type"),
                "params": s.get("params"),
                "returns": s.get("returns"),
                "mark": s.get("mark"),
            }
            for s in services
        ]

        resources_payload = [
            {
                "resource_id": r.get("id"),
                "resource_name": r.get("name"),
                "type": r.get("type"),
                "source_dept_code": r.get("source_dept_code"),
                "source_dept_name": r.get("source_dept_name"),
                "resource_format": r.get("resource_format_text") or r.get("resource_format"),
                "update_cycle": r.get("update_cycle_text") or r.get("update_cycle"),
                "description": r.get("description"),
                "columns": [
                    {
                        "id": col.get("id"),
                        "name": col.get("name"),
                        "name_cn": col.get("name_cn"),
                        "data_format": col.get("data_format_text") or col.get("data_format"),
                        "length": col.get("length"),
                        "security_level": col.get("security_level"),
                        "is_main_column": col.get("is_main_column"),
                        "tag_name": col.get("tag_name"),
                    }
                    for col in bs_resource_columns_index.get(r.get("id"), [])
                ],
            }
            for r in bs_resources
        ]

        catalog_links_payload = [
            {
                "id": c.get("id"),
                "cata_id": c.get("cata_id"),
                "cata_name": c.get("cata_name"),
                "group_code": c.get("group_code"),
                "group_name": c.get("group_name"),
                "org_code": c.get("org_code"),
                "org_name": c.get("org_name"),
                "item_count": coerce_int(c.get("item_count")),
                "res_id": c.get("res_id"),
                "table_name": c.get("table_name"),
            }
            for c in catalog_links
        ]

        schema_metas_payload = [
            {
                "schema_id": sm.get("schema_id"),
                "schema_name": sm.get("schema_name"),
                "authority_org_code": sm.get("authority_org_code"),
                "authority_org_name": sm.get("authority_org_name"),
                "associate_meta_id": sm.get("associate_meta_id"),
                "comment": sm.get("comment"),
                "status": sm.get("status"),
                "resources": [
                    {
                        "resource_id": sr.get("resource_id"),
                        "resource_name": sr.get("resource_name"),
                        "org_code": sr.get("org_code"),
                        "resource_type": sr.get("resource_type"),
                        "status": sr.get("status"),
                    }
                    for sr in schema_resources_index.get(sm.get("schema_id"), [])
                ],
            }
            for sm in schema_metas
        ]

        # 主体 → TopicPackageRecord
        self.topic_repo.create_package(
            {
                "package_code": package_code,
                "title": title,
                "scenario": scenario,
                "owner_org_id": subject.get("lead_org_code"),
                "owner_org_snapshot_json": {
                    "lead_org_code": subject.get("lead_org_code"),
                    "lead_org_name": subject.get("lead_org_name"),
                    "source_org_codes": subject.get("source_org_codes"),
                    "source_org_names": subject.get("source_org_names"),
                },
                "status": "draft",
                "display_snapshot_json": {
                    "subject_id": subject.get("id"),
                    "subject_name": subject.get("name"),
                    "schema_id": subject.get("schema_id"),
                    "standard_id": subject.get("standard_id"),
                    "standard_name": subject.get("standard_name"),
                    "description": subject.get("description"),
                    # business-visible sensitive — read layer applies sensitive_mask
                    "contact": {
                        "contact_name": subject.get("contacter"),
                        "contact_phone": subject.get("contact_phone"),
                    },
                    "create_time": coerce_time(subject.get("create_time")),
                    "objects": objects_payload,
                    "schemas": schemas_payload,
                    "services": services_payload,
                    "resources": resources_payload,
                    "catalog_links": catalog_links_payload,
                    "schema_metas": schema_metas_payload,
                },
                "metric_snapshot_json": {
                    "resource_count": coerce_int(subject.get("resource_count")),
                    "service_count": coerce_int(subject.get("service_count")),
                    "object_count": len(objects_payload),
                    "schema_count": len(schemas_payload),
                },
                "source_ref": f"{legacy_system}:basesubject_info:{package_code}",
            },
            tenant_id=self.tenant_id,
        )

        # items = bs_resource 行（每个主题库下的资源单独建 item，便于按资源粒度授权 / 审计）
        items_payload = [
            {
                "item_code": f"bs_resource:{r.get('id')}",
                "ref_type": "bs_resource",
                "ref_id": str(r.get("id")),
                "title": r.get("name") or f"resource-{r.get('id')}",
                "display_order": idx,
                "summary_json": {
                    "type": r.get("type"),
                    "source_dept_code": r.get("source_dept_code"),
                    "source_dept_name": r.get("source_dept_name"),
                    "resource_format": r.get("resource_format_text") or r.get("resource_format"),
                    "update_cycle": r.get("update_cycle_text") or r.get("update_cycle"),
                    "column_count": len(bs_resource_columns_index.get(r.get("id"), [])),
                },
            }
            for idx, r in enumerate(bs_resources)
        ]
        # default visibility — basesubject 是行业共享，初始默认 sd-default 域内可见
        visibility_payload = [
            {
                "visibility_code": f"{package_code}-default",
                "role_code": "shandong-province",
                "policy_status": "pending_review",
                "condition_json": {"lead_org_code": subject.get("lead_org_code")},
            }
        ]
        configure_payload: dict[str, Any] = {"visibility": visibility_payload}
        if items_payload:
            configure_payload["items"] = items_payload
        self.topic_repo.configure_package(package_code, configure_payload, tenant_id=self.tenant_id)

        # legacy mapping → ObjectMapping，业务 sign-off / 回溯查询用
        self.legacy_repo.upsert_mapping(
            {
                "source_ref": f"{legacy_system}:basesubject_info:{package_code}",
                "legacy_system": legacy_system,
                "legacy_object_type": "basesubject_info",
                "legacy_object_ref": package_code,
                "canonical_type": "TopicPackageRecord",
                "canonical_ref": package_code,
                "evidence_json": {
                    "title": title,
                    "schema_id": subject.get("schema_id"),
                    "object_count": len(objects_payload),
                    "resource_count": len(resources_payload),
                },
            },
            tenant_id=self.tenant_id,
        )


def _group_by(rows: list[dict[str, Any]], key: str) -> dict[Any, list[dict[str, Any]]]:
    """按 key 分组；NULL / 空 key 的 row 被丢弃（避免 None bucket 混淆 join 关联）。"""
    out: dict[Any, list[dict[str, Any]]] = {}
    for row in rows:
        k = row.get(key)
        if k is None or (isinstance(k, str) and not k.strip()):
            continue
        out.setdefault(k, []).append(row)
    return out
