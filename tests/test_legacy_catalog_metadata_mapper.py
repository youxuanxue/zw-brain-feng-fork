"""Regression tests for CatalogMetadataMapper (steps 2-4 of legacy bridging chain)."""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

CATALOG_DUMP = """\
DROP TABLE IF EXISTS `data_catalog`;
CREATE TABLE `data_catalog` (
  `cata_id` varchar(36) NOT NULL,
  `cata_title` varchar(256) DEFAULT NULL,
  `cata_code` varchar(64) NOT NULL,
  `org_code` varchar(64) NOT NULL,
  `region_code` varchar(32) DEFAULT NULL,
  `org_name` varchar(128) NOT NULL,
  `description` text,
  `resource_format` varchar(32) NOT NULL,
  `shared_type` varchar(10) NOT NULL,
  `shared_way` varchar(10) NOT NULL,
  `open_type` tinyint(2) NOT NULL,
  `creator_id` varchar(64) NOT NULL,
  `creator_name` varchar(128) NOT NULL,
  `contact_name` varchar(64) DEFAULT NULL,
  `contact_phone` varchar(64) DEFAULT NULL,
  `status` tinyint(2) NOT NULL DEFAULT '0',
  `cata_version` varchar(10) NOT NULL,
  `create_time` datetime NOT NULL,
  PRIMARY KEY (`cata_id`)
) ENGINE=InnoDB;

INSERT INTO `data_catalog` VALUES \
('cata-1','人口基本信息','BASE-POP-001','11370000MB284651XL','370000','省大数据局','基础人口信息目录','table','1','1',1,'admin','管理员','张三','13800001111',4,'1.0','2025-04-11 11:21:07'),\
('cata-2','企业基本信息','BASE-CORP-001','11370000MB284651XL','370000','省大数据局','基础法人信息目录','table','1','1',1,'admin','管理员',NULL,NULL,1,'1.0','2025-04-11 11:21:07');

DROP TABLE IF EXISTS `data_catalog_column`;
CREATE TABLE `data_catalog_column` (
  `column_id` varchar(32) NOT NULL,
  `cata_id` varchar(36) NOT NULL,
  `name_cn` varchar(256) NOT NULL,
  `data_format` varchar(10) NOT NULL,
  `order_id` int(11) NOT NULL DEFAULT '0',
  `create_time` datetime NOT NULL,
  `sensitive_level` varchar(2) DEFAULT NULL,
  `is_key` varchar(2) DEFAULT NULL,
  `name_en` varchar(255) DEFAULT NULL,
  `length` int(11) DEFAULT NULL,
  PRIMARY KEY (`column_id`)
) ENGINE=InnoDB;

INSERT INTO `data_catalog_column` VALUES \
('col-1','cata-1','姓名','varchar',1,'2025-04-11 11:21:07','3','1','name',64),\
('col-2','cata-1','身份证号','varchar',2,'2025-04-11 11:21:07','5','1','id_card',18),\
('col-3','cata-2','企业名称','varchar',1,'2025-04-11 11:21:07','1','1','corp_name',256);

DROP TABLE IF EXISTS `data_resource`;
CREATE TABLE `data_resource` (
  `res_id` varchar(100) NOT NULL,
  `cata_id` varchar(32) DEFAULT NULL,
  `res_code` varchar(100) DEFAULT NULL,
  `res_name` varchar(256) NOT NULL,
  `res_desc` varchar(512) NOT NULL,
  `res_type` varchar(10) NOT NULL,
  `res_version` varchar(10) NOT NULL,
  `creator_id` varchar(64) NOT NULL,
  `creator_name` varchar(128) NOT NULL,
  `org_id` varchar(128) NOT NULL,
  `org_name` varchar(128) NOT NULL,
  `register_date` datetime NOT NULL,
  `publish_date` datetime DEFAULT NULL,
  `status` tinyint(2) NOT NULL,
  `share_type` varchar(10) NOT NULL,
  `open_type` varchar(10) NOT NULL,
  `owner_org_id` varchar(128) NOT NULL,
  `owner_org_name` varchar(128) NOT NULL,
  `region_code` varchar(32) DEFAULT NULL,
  PRIMARY KEY (`res_id`)
) ENGINE=InnoDB;

INSERT INTO `data_resource` VALUES \
('res-1','cata-1','RES-POP-001','人口基本信息_库表资源','基础人口表','table','1','admin','管理员','11370000MB284651XL','省大数据局','2025-04-01 10:00:00','2025-04-15 10:00:00',5,'1','1','11370000MB284651XL','省大数据局','370000');
"""


METARESOURCE_DUMP = """\
DROP TABLE IF EXISTS `rc_resource`;
CREATE TABLE `rc_resource` (
  `id` varchar(36) NOT NULL,
  `version` int(11) NOT NULL,
  `res_name` varchar(300) NOT NULL,
  `res_desc` varchar(600) DEFAULT NULL,
  `res_type` char(11) DEFAULT NULL,
  `cata_id` varchar(34) DEFAULT NULL,
  `cata_name` varchar(255) DEFAULT NULL,
  `org_id` varchar(50) DEFAULT NULL,
  `region_code` varchar(20) DEFAULT NULL,
  `org_name` varchar(50) DEFAULT NULL,
  `share_type` int(11) DEFAULT NULL,
  `open_type` int(11) DEFAULT NULL,
  `update_cycle` int(11) DEFAULT NULL,
  `creator_id` varchar(50) DEFAULT NULL,
  `creator_name` varchar(50) DEFAULT NULL,
  `create_time` datetime DEFAULT NULL,
  `publish_time` datetime DEFAULT NULL,
  `status` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB;

INSERT INTO `rc_resource` VALUES \
('mr-1',1,'停车场信息_库表资源','停车场列表','table','cata-3','停车场目录','11370000004504927A','370000','省公安厅',1,1,1,'admin','管理员','2025-04-01 10:00:00','2025-04-15 10:00:00',4);

DROP TABLE IF EXISTS `rc_resource_table`;
CREATE TABLE `rc_resource_table` (
  `id` varchar(36) NOT NULL,
  `resource_id` varchar(36) NOT NULL,
  `table_id` varchar(36) NOT NULL,
  `table_name` varchar(128) NOT NULL,
  `database_id` varchar(36) DEFAULT NULL,
  `exchange_type` varchar(32) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB;

INSERT INTO `rc_resource_table` VALUES \
('bind-1','mr-1','table-1','t_parking','db-1','table');

DROP TABLE IF EXISTS `rc_resource_catalog_item_link`;
CREATE TABLE `rc_resource_catalog_item_link` (
  `id` varchar(36) NOT NULL,
  `catalog_id` varchar(36) NOT NULL,
  `catalog_item_id` varchar(36) NOT NULL,
  `resource_id` varchar(36) NOT NULL,
  `table_id` varchar(36) NOT NULL,
  `table_column_id` varchar(36) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB;

INSERT INTO `rc_resource_catalog_item_link` VALUES \
('map-1','cata-1','col-1','mr-1','bind-1','field-name');

DROP TABLE IF EXISTS `meta_baseinfo`;
CREATE TABLE `meta_baseinfo` (
  `meta_id` varchar(36) NOT NULL,
  `resource_id` varchar(36) NOT NULL,
  `meta_name` varchar(128) NOT NULL,
  `model_id` varchar(36) DEFAULT NULL,
  `version` varchar(16) DEFAULT NULL,
  `table_name` varchar(128) DEFAULT NULL,
  `create_time` datetime DEFAULT NULL,
  PRIMARY KEY (`meta_id`)
) ENGINE=InnoDB;

INSERT INTO `meta_baseinfo` VALUES \
('meta-1','mr-1','停车场表','model-1','1','t_parking','2025-04-11 11:21:07');

DROP TABLE IF EXISTS `meta_gather_task`;
CREATE TABLE `meta_gather_task` (
  `task_id` varchar(36) NOT NULL,
  `resource_id` varchar(36) NOT NULL,
  `job_id` varchar(36) DEFAULT NULL,
  `status` varchar(32) DEFAULT NULL,
  `create_time` datetime DEFAULT NULL,
  `finish_time` datetime DEFAULT NULL,
  PRIMARY KEY (`task_id`)
) ENGINE=InnoDB;

INSERT INTO `meta_gather_task` VALUES \
('gather-1','mr-1','job-1','success','2025-04-11 11:21:07','2025-04-11 11:22:07');

DROP TABLE IF EXISTS `meta_relation`;
CREATE TABLE `meta_relation` (
  `id` varchar(36) NOT NULL,
  `source_meta_id` varchar(36) DEFAULT NULL,
  `target_meta_id` varchar(36) DEFAULT NULL,
  `relation_from` varchar(32) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB;

INSERT INTO `meta_relation` VALUES \
('rel-1','meta-1','meta-2','imported');

DROP TABLE IF EXISTS `catalog_quality_result`;
CREATE TABLE `catalog_quality_result` (
  `id` varchar(36) NOT NULL,
  `cata_id` varchar(36) DEFAULT NULL,
  `status` varchar(32) DEFAULT NULL,
  `score` int DEFAULT NULL,
  `summary` varchar(128) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB;

INSERT INTO `catalog_quality_result` VALUES \
('quality-1','cata-1','pass',95,'字段挂接完整');
"""


def test_catalog_metadata_mapper_imports_catalog_resource_and_items() -> None:
    with TemporaryDirectory() as tmp:
        dumps_dir = Path(tmp) / "dumps"
        dumps_dir.mkdir()
        (dumps_dir / "dump-dsp_catalog-202604000000.sql").write_text(CATALOG_DUMP, encoding="utf-8")
        (dumps_dir / "dump-dsp_metaresource-202604000000.sql").write_text(METARESOURCE_DUMP, encoding="utf-8")

        os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "smoke.db")
        os.environ["ZW_BRAIN_LEGACY_DUMPS_DIR"] = str(dumps_dir)
        os.environ["ZW_BRAIN_LEGACY_CACHE_DIR"] = str(Path(tmp) / "cache")

        from zw_brain.adapters.legacy import LegacyImportRunner
        from zw_brain.domain.repositories.catalog import CatalogRepository
        from zw_brain.domain.repositories.external_adapter import ExternalAdapterRepository
        from zw_brain.domain.repositories.legacy_mapping import LegacyObjectMappingRepository
        from zw_brain.domain.repositories.metadata_evidence import MetadataEvidenceRepository
        from zw_brain.domain.repositories.resource_api import ResourceApiRepository
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        runner = LegacyImportRunner()

        # Step 2: rc_resource first (resources before catalogs)
        meta_stats = runner.import_schema("dsp_metaresource")
        assert meta_stats.to_dict()["counts"] == {
            "catalog_quality_result.imported": 1,
            "meta_baseinfo.imported": 1,
            "meta_gather_task.imported": 1,
            "meta_relation.imported": 1,
            "rc_resource.imported": 1,
            "rc_resource_catalog_item_link.imported": 1,
            "rc_resource_table.imported": 1,
        }

        # Step 3+4: data_catalog + data_catalog_column + data_resource
        # dsp_catalog runs both catalog_metadata and exchange mappers; the test dump
        # contains no apply rows so the exchange-mapper stats here are 0 imported.
        cat_results = runner.import_schema("dsp_catalog")
        cat_stats = next(s for s in cat_results if "data_catalog.imported" in s.to_dict()["counts"])
        assert cat_stats.to_dict()["counts"] == {
            "data_catalog.imported": 2,
            "data_catalog_column.imported": 3,
            "data_resource.imported": 1,
        }

        # CatalogEntry uses cata_code as catalog_code; lifecycle mapped from numeric status
        catalog_repo = CatalogRepository()
        entries = {e.catalog_code: e for e in catalog_repo.list_entries(tenant_id="sd-default")}
        assert "BASE-POP-001" in entries
        assert entries["BASE-POP-001"].title == "人口基本信息"
        assert entries["BASE-POP-001"].lifecycle_status == "active"  # 4 → active
        assert entries["BASE-CORP-001"].lifecycle_status == "pending_review"  # 1 → pending_review
        # contact phone (business-visible sensitive) flows into summary_json (under nested
        # `summary` key — CatalogRepository.upsert_from_resource echoes the whole payload).
        # Mask layer is read-side.
        assert entries["BASE-POP-001"].summary_json["summary"]["contact"]["contact_phone"] == "13800001111"

        # CatalogItem rows
        items = {i.item_code: i for i in catalog_repo.list_items("cata-1", tenant_id="sd-default")}
        assert {"col-1", "col-2"} == set(items.keys())
        assert items["col-1"].title == "姓名"
        assert items["col-1"].summary_json["sensitive_level"] == "3"

        # ResourceAsset from both dumps
        resource_repo = ResourceApiRepository()
        assets = {a.resource_code: a for a in resource_repo.list_assets(tenant_id="sd-default")}
        # data_resource (catalog dump) — uses res_code → "RES-POP-001"
        assert "RES-POP-001" in assets
        assert assets["RES-POP-001"].resource_kind == "table"
        assert assets["RES-POP-001"].lifecycle_status == "revoked"  # 5 → revoked
        # rc_resource (metaresource dump) — uses id as resource_code
        assert "mr-1" in assets
        assert assets["mr-1"].owner_org_id == "11370000004504927A"  # 省公安厅
        assert assets["mr-1"].lifecycle_status == "active"  # 4 → active
        bindings = {b.binding_code: b for b in resource_repo.list_bindings(tenant_id="sd-default")}
        assert bindings["table-1"].resource_code == "mr-1"
        assert bindings["table-1"].schema_ref["table_name"] == "t_parking"

        metadata = MetadataEvidenceRepository()
        mappings = metadata.list_schema_mappings(tenant_id="sd-default")
        assert len(mappings) == 1
        assert mappings[0].catalog_item_code == "col-1"
        assert mappings[0].resource_code == "mr-1"
        assert metadata.list_schema_snapshots(tenant_id="sd-default")[0].resource_code == "mr-1"
        assert metadata.list_gather_evidence(tenant_id="sd-default")[0].status == "succeeded"
        assert metadata.list_lineage_relations(tenant_id="sd-default")[0].relation_ref == "rel-1"
        assert metadata.list_quality_evidence(tenant_id="sd-default")[0].quality_status == "passed"

        # Legacy mappings recorded
        legacy = LegacyObjectMappingRepository()
        catalog_maps = legacy.list_mappings(tenant_id="sd-default", canonical_type="catalog_entry")
        assert {m.legacy_object_ref for m in catalog_maps} == {"cata-1", "cata-2"}
        resource_maps = legacy.list_mappings(tenant_id="sd-default", canonical_type="resource_asset")
        assert {m.legacy_object_ref for m in resource_maps} == {"res-1", "mr-1"}

        # Two AdapterRunRecords (one per schema), both succeeded
        runs = ExternalAdapterRepository().list_run_records(
            tenant_id="sd-default", adapter_slug="legacy.catalog_metadata.import"
        )
        assert len(runs) == 2
        assert all(r.status == "succeeded" for r in runs)
