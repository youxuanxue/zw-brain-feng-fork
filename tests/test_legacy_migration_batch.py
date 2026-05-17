from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import dedent

import pytest

from zw_brain.adapters.legacy.migration_batch import MigrationError, MigrationOptions, run_acceptance_migration, run_migration


def _write_core_dumps(dumps_dir: Path) -> None:
    dumps_dir.mkdir()
    (dumps_dir / "dump-dsp_bsp-202604000000.sql").write_text(
        dedent(
            """
            DROP TABLE IF EXISTS `pub_organ`;
            CREATE TABLE `pub_organ` (
              `CODE` varchar(64),
              `NAME` varchar(128),
              `TRACE_CODE` varchar(128),
              `REGION_CODE` varchar(32),
              `STATUS` int,
              PRIMARY KEY (`CODE`)
            ) ENGINE=InnoDB;
            INSERT INTO `pub_organ` VALUES ('ORG-1','省大数据局',NULL,'370000',1);
            DROP TABLE IF EXISTS `pub_region`;
            CREATE TABLE `pub_region` (
              `CODE` varchar(64),
              `NAME` varchar(128),
              `PARENT_CODE` varchar(64),
              `GRADE` varchar(32),
              `STATUS` int,
              PRIMARY KEY (`CODE`)
            ) ENGINE=InnoDB;
            INSERT INTO `pub_region` VALUES ('370000','山东省',NULL,'province',1);
            DROP TABLE IF EXISTS `pub_user`;
            CREATE TABLE `pub_user` (
              `ID` varchar(64),
              `ACCOUNT` varchar(64),
              `NAME` varchar(128),
              `ORG_CODE` varchar(64),
              `ROLE_VALUE` varchar(64),
              `STATUS` int,
              PRIMARY KEY (`ID`)
            ) ENGINE=InnoDB;
            INSERT INTO `pub_user` VALUES ('u-1','admin','管理员','ORG-1','r1',1);
            DROP TABLE IF EXISTS `pub_role`;
            CREATE TABLE `pub_role` (
              `ID` varchar(64),
              `VALUE` varchar(64),
              `NAME` varchar(128),
              `STATUS` int,
              PRIMARY KEY (`ID`)
            ) ENGINE=InnoDB;
            INSERT INTO `pub_role` VALUES ('role-1','r1','申请人',1);
            """
        ).strip(),
        encoding="utf-8",
    )
    (dumps_dir / "dump-dsp_catalog-202604000000.sql").write_text(
        dedent(
            """
            DROP TABLE IF EXISTS `data_catalog`;
            CREATE TABLE `data_catalog` (
              `cata_id` varchar(36),
              `cata_title` varchar(256),
              `cata_code` varchar(64),
              `org_code` varchar(64),
              `region_code` varchar(32),
              `org_name` varchar(128),
              `description` text,
              `resource_format` varchar(32),
              `shared_type` varchar(10),
              `shared_way` varchar(10),
              `open_type` tinyint,
              `creator_id` varchar(64),
              `creator_name` varchar(128),
              `contact_name` varchar(64),
              `contact_phone` varchar(64),
              `status` tinyint,
              `cata_version` varchar(10),
              `create_time` datetime,
              PRIMARY KEY (`cata_id`)
            ) ENGINE=InnoDB;
            INSERT INTO `data_catalog` VALUES ('cata-1','人口基本信息','BASE-POP-001','ORG-1','370000','省大数据局','基础人口信息目录','table','1','1',1,'admin','管理员','张三','13800001111',4,'1.0','2025-04-11 11:21:07'),('085CB5C3D29C4B59A3902993669CEFBC','区县域医疗机构院主要业务情况统计表','307013370000308002000000/000049','ORG-1','370000000000','省大数据局','区县域医疗机构院主要业务情况统计表','table','1','0204',1,'admin','管理员',NULL,NULL,4,'1.0','2025-04-11 11:21:07');
            DROP TABLE IF EXISTS `data_catalog_column`;
            CREATE TABLE `data_catalog_column` (
              `column_id` varchar(32),
              `cata_id` varchar(36),
              `name_cn` varchar(256),
              `data_format` varchar(10),
              `order_id` int,
              `create_time` datetime,
              `sensitive_level` varchar(2),
              `is_key` varchar(2),
              `name_en` varchar(255),
              `length` int,
              PRIMARY KEY (`column_id`)
            ) ENGINE=InnoDB;
            INSERT INTO `data_catalog_column` VALUES ('col-1','cata-1','姓名','varchar',1,'2025-04-11 11:21:07','3','1','name',64),('5DA3A0BBA68847BEAC10FE20ECDCC40E','085CB5C3D29C4B59A3902993669CEFBC','出院者平均住院日','varchar',1,'2025-04-11 11:21:07','2','0','avg_hospital_days',32);
            DROP TABLE IF EXISTS `data_resource`;
            CREATE TABLE `data_resource` (
              `res_id` varchar(100),
              `cata_id` varchar(32),
              `res_code` varchar(100),
              `res_name` varchar(256),
              `res_desc` varchar(512),
              `res_type` varchar(10),
              `res_version` varchar(10),
              `creator_id` varchar(64),
              `creator_name` varchar(128),
              `org_id` varchar(128),
              `org_name` varchar(128),
              `register_date` datetime,
              `publish_date` datetime,
              `status` tinyint,
              `share_type` varchar(10),
              `open_type` varchar(10),
              `owner_org_id` varchar(128),
              `owner_org_name` varchar(128),
              `region_code` varchar(32),
              PRIMARY KEY (`res_id`)
            ) ENGINE=InnoDB;
            INSERT INTO `data_resource` VALUES ('res-1','cata-1','RES-POP-001','人口基本信息_库表资源','基础人口表','table','1','admin','管理员','ORG-1','省大数据局','2025-04-01 10:00:00','2025-04-15 10:00:00',4,'1','1','ORG-1','省大数据局','370000'),('66dd29e00efe45729babe2c5bba118fa','085CB5C3D29C4B59A3902993669CEFBC','66dd29e00efe45729babe2c5bba118fa','区县域医疗机构院主要业务情况统计表_库表资源','医疗机构统计表','table','1','admin','管理员','ORG-1','省大数据局','2025-04-01 10:00:00','2025-04-15 10:00:00',4,'1','1','ORG-1','省大数据局','370000000000');
            DROP TABLE IF EXISTS `data_basic_elem_catalog`;
            CREATE TABLE `data_basic_elem_catalog` (
              `cata_id` varchar(36),
              `version` int,
              `cata_title` varchar(256),
              `category_id` varchar(36),
              `category_code` varchar(36),
              `domain_id` varchar(36),
              `level` varchar(10),
              `source_service_item_catalog_name` varchar(256),
              `source_service_item_catalog_code` varchar(50),
              `description` text,
              `business_line_code` int,
              `imported_by_org_code` varchar(64),
              `imported_by_org_name` varchar(128),
              `create_userid` varchar(50),
              `create_time` datetime,
              `update_time` datetime,
              PRIMARY KEY (`cata_id`,`version`)
            ) ENGINE=InnoDB;
            INSERT INTO `data_basic_elem_catalog` VALUES ('0b26783950004ed882ec9309fae73310',1,'医疗救助信息','cat-med','307013','domain-med','1,2,3,null','低保、特困等困难群众医疗救助','svc-med','人员姓名',1,'ORG-1','省大数据局','admin','2025-04-11 11:21:07','2025-04-11 11:21:07');
            DROP TABLE IF EXISTS `data_basic_elem_catalog_item`;
            CREATE TABLE `data_basic_elem_catalog_item` (
              `cata_id` varchar(36),
              `cata_version` int,
              `column_code` varchar(50),
              `name_cn` varchar(256),
              `data_format` varchar(10),
              `create_time` datetime,
              PRIMARY KEY (`cata_id`,`cata_version`,`column_code`)
            ) ENGINE=InnoDB;
            INSERT INTO `data_basic_elem_catalog_item` VALUES ('0b26783950004ed882ec9309fae73310',1,'name','人员姓名','varchar','2025-04-11 11:21:07');
            DROP TABLE IF EXISTS `data_apply`;
            CREATE TABLE `data_apply` (
              `id` varchar(32),
              `cata_id` varchar(32),
              `resource_id` varchar(32),
              `resource_name` varchar(255),
              `app_key` varchar(255),
              `org_id` varchar(32),
              `org_name` varchar(255),
              `apply_org_id` varchar(32),
              `apply_org_name` varchar(255),
              `contact` varchar(255),
              `phone` varchar(255),
              `email` varchar(255),
              `use_contact` varchar(255),
              `use_phone` varchar(255),
              `use_email` varchar(255),
              `deptid` varchar(32),
              `dept` varchar(255),
              `use_reason` varchar(255),
              `other_reason` varchar(255),
              `use_region` varchar(255),
              `use_item` varchar(255),
              `system_id` varchar(32),
              `system_name` varchar(255),
              `system_type` varchar(32),
              `is_proxy` varchar(10),
              `service_apply_id` varchar(32),
              `service_type` varchar(32),
              `service_times` int,
              `service_most_times` int,
              `service_times_unit` varchar(32),
              `service_usetime` varchar(32),
              `service_usedays` int,
              `type` varchar(32),
              `resource_status` varchar(32),
              `batch_id` varchar(32),
              `flow_code` varchar(32),
              `has_condition` varchar(10),
              `create_time` datetime,
              `apply_basis` varchar(255),
              `status` int,
              PRIMARY KEY (`id`)
            ) ENGINE=InnoDB;
            INSERT INTO `data_apply` VALUES ('e0912847f2014b8098c42a6437a8838d','085CB5C3D29C4B59A3902993669CEFBC','3372a2b1ebe14b15911e7d45a799ea23','区县域医疗机构院主要业务情况统计表_文件资源',NULL,'ORG-1','省大数据局','ORG-1','省大数据局',NULL,NULL,NULL,NULL,NULL,NULL,'ORG-1','省大数据局','业务协同',NULL,'山东省','出院者平均住院日',NULL,NULL,NULL,NULL,NULL,'file',NULL,NULL,NULL,NULL,NULL,'file','active',NULL,NULL,NULL,'2025-04-11 11:21:07','业务协同',9);
            DROP TABLE IF EXISTS `data_apply_course`;
            CREATE TABLE `data_apply_course` (
              `id` varchar(32),
              `apply_id` varchar(32),
              `status` int,
              `check_status` int,
              `node_name` varchar(128),
              `opinion` varchar(255),
              `org_id` varchar(32),
              `org_name` varchar(255),
              `user_code` varchar(32),
              `user_name` varchar(255),
              `approve_person` varchar(255),
              `approve_phone` varchar(255),
              `flow_code` varchar(32),
              `flow_name` varchar(128),
              `attachment` varchar(255),
              `create_time` datetime,
              PRIMARY KEY (`id`)
            ) ENGINE=InnoDB;
            INSERT INTO `data_apply_course` VALUES ('bd614d9423cf45af8689a8283d8b7c81','e0912847f2014b8098c42a6437a8838d',1,1,'审核','审核通过','ORG-1','省大数据局','admin','管理员','管理员',NULL,'flow-1','资源申请','', '2025-04-11 11:21:07');
            """
        ).strip(),
        encoding="utf-8",
    )
    (dumps_dir / "dump-dsp_metaresource-202604000000.sql").write_text(
        dedent(
            """
            DROP TABLE IF EXISTS `rc_resource`;
            CREATE TABLE `rc_resource` (
              `id` varchar(36),
              `version` int,
              `res_name` varchar(300),
              `res_desc` varchar(600),
              `res_type` char(11),
              `cata_id` varchar(34),
              `cata_name` varchar(255),
              `org_id` varchar(50),
              `region_code` varchar(20),
              `org_name` varchar(50),
              `share_type` int,
              `open_type` int,
              `update_cycle` int,
              `creator_id` varchar(50),
              `creator_name` varchar(50),
              `create_time` datetime,
              `publish_time` datetime,
              `status` int,
              PRIMARY KEY (`id`)
            ) ENGINE=InnoDB;
            INSERT INTO `rc_resource` VALUES ('mr-1',1,'停车场信息_库表资源','停车场列表','table','cata-1','人口基本信息','ORG-1','370000','省大数据局',1,1,1,'admin','管理员','2025-04-01 10:00:00','2025-04-15 10:00:00',4),('66dd29e00efe45729babe2c5bba118fa',1,'区县域医疗机构院主要业务情况统计表_库表资源','医疗机构统计表','table','085CB5C3D29C4B59A3902993669CEFBC','区县域医疗机构院主要业务情况统计表','ORG-1','370000000000','省大数据局',1,1,1,'admin','管理员','2025-04-01 10:00:00','2025-04-15 10:00:00',4);
            DROP TABLE IF EXISTS `rc_resource_table`;
            CREATE TABLE `rc_resource_table` (
              `id` varchar(36),
              `resource_id` varchar(36),
              `table_id` varchar(36),
              `table_name` varchar(128),
              `database_id` varchar(36),
              `exchange_type` varchar(32),
              PRIMARY KEY (`id`)
            ) ENGINE=InnoDB;
            INSERT INTO `rc_resource_table` VALUES ('bind-1','mr-1','table-1','t_population','db-1','table'),('ac8e87b0e98140e7a3e35a0a6ac697ed','66dd29e00efe45729babe2c5bba118fa','ac8e87b0e98140e7a3e35a0a6ac697ed','t_medical_org_stats','db-1','table');
            DROP TABLE IF EXISTS `rc_resource_catalog_item_link`;
            CREATE TABLE `rc_resource_catalog_item_link` (
              `id` varchar(36),
              `catalog_id` varchar(36),
              `catalog_item_id` varchar(36),
              `resource_id` varchar(36),
              `table_id` varchar(36),
              `table_column_id` varchar(36),
              PRIMARY KEY (`id`)
            ) ENGINE=InnoDB;
            INSERT INTO `rc_resource_catalog_item_link` VALUES ('map-1','cata-1','col-1','mr-1','bind-1','field-name'),('59ce38319b7f4defabec063da61f37f6','085CB5C3D29C4B59A3902993669CEFBC','5DA3A0BBA68847BEAC10FE20ECDCC40E','66dd29e00efe45729babe2c5bba118fa','ac8e87b0e98140e7a3e35a0a6ac697ed','fdcdc442107540e5a0b10c9385b2775d');
            DROP TABLE IF EXISTS `meta_baseinfo`;
            CREATE TABLE `meta_baseinfo` (
              `meta_id` varchar(36),
              `resource_id` varchar(36),
              `meta_name` varchar(128),
              `model_id` varchar(36),
              `version` varchar(16),
              `table_name` varchar(128),
              `create_time` datetime,
              PRIMARY KEY (`meta_id`)
            ) ENGINE=InnoDB;
            INSERT INTO `meta_baseinfo` VALUES ('meta-1','mr-1','人口表','model-1','1','t_population','2025-04-11 11:21:07'),('meta-med-1','66dd29e00efe45729babe2c5bba118fa','区县域医疗机构统计表','model-med','1','t_medical_org_stats','2025-04-11 11:21:07');
            DROP TABLE IF EXISTS `meta_gather_task`;
            CREATE TABLE `meta_gather_task` (
              `task_id` varchar(36),
              `resource_id` varchar(36),
              `job_id` varchar(36),
              `status` varchar(32),
              `create_time` datetime,
              `finish_time` datetime,
              PRIMARY KEY (`task_id`)
            ) ENGINE=InnoDB;
            INSERT INTO `meta_gather_task` VALUES ('gather-1','mr-1','job-1','success','2025-04-11 11:21:07','2025-04-11 11:22:07');
            DROP TABLE IF EXISTS `meta_relation`;
            CREATE TABLE `meta_relation` (
              `id` varchar(36),
              `source_meta_id` varchar(36),
              `target_meta_id` varchar(36),
              `relation_from` varchar(32),
              PRIMARY KEY (`id`)
            ) ENGINE=InnoDB;
            INSERT INTO `meta_relation` VALUES ('rel-1','meta-1','meta-2','imported');
            DROP TABLE IF EXISTS `catalog_quality_result`;
            CREATE TABLE `catalog_quality_result` (
              `id` varchar(36),
              `cata_id` varchar(36),
              `status` varchar(32),
              `score` int,
              `summary` varchar(128),
              PRIMARY KEY (`id`)
            ) ENGINE=InnoDB;
            INSERT INTO `catalog_quality_result` VALUES ('quality-1','cata-1','pass',95,'字段挂接完整');
            """
        ).strip(),
        encoding="utf-8",
    )
    for schema in ("dsp_require", "dsp_handling", "dsp_example", "dsp_connect", "dsp_service", "dsp_pipelines", "dsp_monitor", "dsp_perform"):
        (dumps_dir / f"dump-{schema}-202604000000.sql").write_text("", encoding="utf-8")


def test_legacy_migration_batch_strict_report_and_no_legacy_runtime() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        dumps_dir = root / "dumps"
        db_path = root / "customer.db"
        _write_core_dumps(dumps_dir)
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)
        os.environ["ZW_BRAIN_TENANT_ID"] = "sd-default"
        os.environ["ZW_BRAIN_LEGACY_DUMPS_DIR"] = str(dumps_dir)
        report = run_migration(
            MigrationOptions(
                dumps_dir=dumps_dir,
                db_path=db_path,
                reset_db=True,
                strict=True,
            )
        )
        assert report["status"] == "succeeded"
        assert report["dumps"]["dsp_catalog"]["sha256"]
        assert report["verification"]["canonical_counts"]["catalog_entry"] >= 3
        assert report["verification"]["canonical_counts"]["catalog_item"] >= 3
        assert report["verification"]["canonical_counts"]["resource_asset"] >= 3
        assert report["verification"]["canonical_counts"]["resource_channel_binding"] >= 2
        assert report["verification"]["canonical_counts"]["application_record"] >= 1
        assert report["verification"]["canonical_counts"]["delivery_task"] >= 1
        assert report["verification"]["canonical_counts"]["approval_case"] >= 1
        assert report["verification"]["canonical_counts"]["resource_schema_mapping"] == 2
        assert report["verification"]["canonical_counts"]["resource_schema_snapshot"] == 2
        assert report["verification"]["canonical_counts"]["metadata_gather_evidence_projection"] == 1
        assert report["verification"]["canonical_counts"]["lineage_relation_projection"] == 1
        assert report["verification"]["canonical_counts"]["quality_evidence_projection"] == 1
        assert not [item for item in report["table_accounting"] if item["unaccounted_rows"]]
        assert "13800001111" not in json.dumps(report, ensure_ascii=False)

        from zw_brain.domain.repositories.catalog import CatalogRepository
        from zw_brain.domain.repositories.legacy_mapping import LegacyObjectMappingRepository
        from zw_brain.domain.repositories.metadata_evidence import MetadataEvidenceRepository
        from zw_brain.domain.repositories.resource_api import ResourceApiRepository

        legacy = LegacyObjectMappingRepository()
        assert legacy.resolve_canonical_ref(
            legacy_system="dsp-catalog3",
            legacy_object_type="data_catalog",
            legacy_object_ref="cata-1",
            canonical_type="catalog_entry",
            tenant_id="sd-default",
        ) == "BASE-POP-001"
        assert ResourceApiRepository().get_asset("mr-1").catalog_code == "BASE-POP-001"
        assert ResourceApiRepository().get_asset("66dd29e00efe45729babe2c5bba118fa").catalog_code == "307013370000308002000000/000049"
        assert [item.mapping_code for item in MetadataEvidenceRepository().list_schema_mappings(catalog_code="BASE-POP-001")] == ["map-1"]
        r1_mappings = MetadataEvidenceRepository().list_schema_mappings(catalog_code="307013370000308002000000/000049")
        assert [item.mapping_code for item in r1_mappings] == ["59ce38319b7f4defabec063da61f37f6"]
        assert legacy.resolve_canonical_ref(
            legacy_system="dsp-catalog3",
            legacy_object_type="data_catalog",
            legacy_object_ref="085CB5C3D29C4B59A3902993669CEFBC",
            canonical_type="catalog_entry",
            tenant_id="sd-default",
        ) == "307013370000308002000000/000049"
        assert legacy.resolve_canonical_ref(
            legacy_system="dsp-catalog3",
            legacy_object_type="data_basic_elem_catalog",
            legacy_object_ref="0b26783950004ed882ec9309fae73310",
            canonical_type="catalog_entry",
            tenant_id="sd-default",
        ) == "basic-elem:0b26783950004ed882ec9309fae73310"
        basic_items = CatalogRepository().list_items("basic-elem:0b26783950004ed882ec9309fae73310", tenant_id="sd-default")
        assert [item.title for item in basic_items] == ["人员姓名"]
        assert legacy.resolve_canonical_ref(
            legacy_system="dsp-catalog3",
            legacy_object_type="data_apply",
            legacy_object_ref="e0912847f2014b8098c42a6437a8838d",
            canonical_type="application_record",
            tenant_id="sd-default",
        ) == "e0912847f2014b8098c42a6437a8838d"
        assert legacy.resolve_canonical_ref(
            legacy_system="dsp-catalog3",
            legacy_object_type="data_apply",
            legacy_object_ref="e0912847f2014b8098c42a6437a8838d",
            canonical_type="DeliveryTaskRecord",
            tenant_id="sd-default",
        ) == "e0912847f2014b8098c42a6437a8838d"

        for entry in dumps_dir.iterdir():
            entry.unlink()
        from zw_brain.command.runtime import get_service, reset_service

        reset_service()
        service = get_service()
        result = service.invoke_skill("catalog.browse", {"lifecycle": "all"})
        assert any(item["catalog_code"] == "BASE-POP-001" for item in result["items"])
        entry = service.invoke_skill("catalog.entry.query", {"catalog_code": "BASE-POP-001"})
        assert "13800001111" not in json.dumps(result, ensure_ascii=False)
        assert "13800001111" not in json.dumps(entry, ensure_ascii=False)
        metadata = service.invoke_skill("metadata.catalog_item.query", {})
        assert metadata["total"] == 2
        assert {item["mapping_code"] for item in metadata["items"]} == {"map-1", "59ce38319b7f4defabec063da61f37f6"}
        metadata_by_catalog = service.invoke_skill("metadata.catalog_item.query", {"catalog_code": "BASE-POP-001"})
        assert metadata_by_catalog["total"] == 1
        assert metadata_by_catalog["items"][0]["mapping_code"] == "map-1"
        reset_service()


def test_legacy_acceptance_runs_dry_apply_repeat_and_reports_idempotency() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        dumps_dir = root / "dumps"
        db_path = root / "customer.db"
        _write_core_dumps(dumps_dir)
        report = run_acceptance_migration(MigrationOptions(dumps_dir=dumps_dir, db_path=db_path, strict=True))
        assert report["status"] == "succeeded"
        assert report["acceptance"]["flow"] == ["dry_run", "apply", "repeat_apply"]
        assert report["acceptance"]["stage_statuses"] == {"dry_run": "succeeded", "apply": "succeeded", "repeat_apply": "succeeded"}
        assert report["stages"]["dry_run"]["dry_run"] is True
        assert report["stages"]["apply"]["reset_db"] is False
        assert report["stages"]["repeat_apply"]["reset_db"] is False
        reset_report = run_acceptance_migration(MigrationOptions(dumps_dir=dumps_dir, db_path=db_path, reset_db=True, strict=True))
        assert reset_report["stages"]["apply"]["reset_db"] is True
        assert reset_report["status"] == "succeeded"
        assert report["acceptance"]["idempotency"]["verified"] is True
        assert report["acceptance"]["missing_dumps"] == []
        assert report["acceptance"]["unmapped_tables"] == []
        assert report["acceptance"]["sensitive_policy"]["report_sanitized"] is True
        assert "13800001111" not in json.dumps(report, ensure_ascii=False)


@pytest.mark.legacy_migration_acceptance
def test_r2_parking_real_dump_migrates_approval_grant_and_legacy_mappings() -> None:
    from sqlalchemy import select

    from zw_brain.domain.models import (
        ApplicationRecord,
        ApprovalCaseRecord,
        ApprovalDecisionRecord,
        ApprovalStepRecord,
        CatalogEntryRecord,
        CatalogItemRecord,
        DeliveryAttemptRecord,
        DeliveryExecutionEvidenceRecord,
        DeliverySubscriptionRecord,
        DeliveryTaskRecord,
        LegacyObjectMappingRecord,
        ResourceAssetRecord,
        ResourceChannelBindingRecord,
        ResourceSchemaMappingRecord,
        ResourceSchemaSnapshotRecord,
        TopicPackageItemRecord,
        TopicPackageRecord,
        TopicPackageVisibilityRecord,
    )
    from zw_brain.shared.db import create_session_factory

    apply_id = "86013a7aaaf74724b7eb156272292e24"
    authz_id = "d9c1d5149c634c1ab602fc47867712f1"
    catalog_id = "8A1E10FD052C467EBBCD40F832830D33"
    catalog_code = "370000308004000000/000001"
    resource_id = "39a41e4b4e80439187e0f86218bae5d9"
    name_item = "7DF8E3C04F0A4D69B8152D3A84742811"
    address_item = "172970772AE541B0A5A899A39927A583"
    name_mapping = "2666e3477463449b84bc6d67092e7831"
    address_mapping = "6be22f7d0cc641c28ef30d997d5e0a50"
    course_ids = {
        "1889dc190d6245ffa653bfff7356bdf1",
        "9014ea9995504233aac90eb363eae702",
        "ebe7af125a964e7ebc2bac038612cff8",
        "bd97908f1d864890859b7a950b068b44",
    }
    industry_catalog_id = "E4C4245BC9DC45E7B6F9530C6ABFB226"
    industry_catalog_code = "307013370000308002000000/000001"
    industry_table_resource_id = "6867b719babe4dbabc9161774afb0e8e"
    industry_file_resource_id = "e7eda94489234d58a013cfc2565b2adb"
    industry_url_resource_id = "b6f558a573724c9598109ce39c72a7e8"
    industry_table_binding = "cb9e2aa7832048baa891f1d1333212c5"
    industry_file_binding = "a78adb83a69e4adc9f767e0a7c24b749"
    coding_catalog_id = "00C168BD1E694F2FAC58330FF7338B5D"
    coding_catalog_code = "307013370000308002000000/000064"
    coding_resource_id = "1859cf4c2201407a88e4393d4301f8fc"
    legal_person_catalog_id = "C5050A0F51F348968591DC13E47C6A9D"
    legal_person_catalog_code = "307013370000303000000000\\/000002"
    legal_person_resource_id = "2238229a-d571-4419-82fa-934969ca9f48"
    legal_person_group_id = "102"
    legal_person_group_package = f"catalog-group:{legal_person_group_id}"
    materialized_catalog_id = "085CB5C3D29C4B59A3902993669CEFBC"
    materialized_resource_id = "66dd29e00efe45729babe2c5bba118fa"
    dumps_dir = Path(__file__).resolve().parents[1] / "old/10示例数据"

    with TemporaryDirectory() as tmp:
        report = run_acceptance_migration(
            MigrationOptions(dumps_dir=dumps_dir, db_path=Path(tmp) / "r2-parking.db", reset_db=True, strict=True)
        )
        assert report["status"] == "succeeded"
        assert report["acceptance"]["idempotency"]["verified"] is True
        assert report["acceptance"]["missing_dumps"] == []
        assert report["acceptance"]["unmapped_tables"] == []
        assert report["acceptance"]["sensitive_policy"]["report_sanitized"] is True
        assert report["stages"]["apply"]["dumps"]["dsp_catalog"]["tables"].get("data_apply_renewal", 0) == 0
        assert report["stages"]["apply"]["verification"]["canonical_counts"]["approval_step"] >= 4
        assert report["stages"]["apply"]["verification"]["canonical_counts"]["approval_decision"] >= 4

        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            app = session.execute(
                select(ApplicationRecord).where(ApplicationRecord.tenant_id == "sd-default", ApplicationRecord.application_code == apply_id)
            ).scalar_one()
            assert app.status == "approved"
            assert app.payload_json["kind"] == "apply"
            assert app.payload_json["catalog_id"] == catalog_id
            assert app.payload_json["resourceId"] == resource_id
            assert app.payload_json["service_times"] == "1"
            assert app.payload_json["service_most_times"] == "1"
            assert app.payload_json["service_usetime"] == "每日（8:00-18:00)"
            assert app.payload_json["service_usedays"] == "1"
            assert "app_key" not in app.payload_json

            case = session.execute(
                select(ApprovalCaseRecord).where(ApprovalCaseRecord.tenant_id == "sd-default", ApprovalCaseRecord.application_code == apply_id)
            ).scalar_one()
            assert case.current_status == "approved"
            assert case.current_step == 4
            steps = list(
                session.execute(
                    select(ApprovalStepRecord)
                    .where(ApprovalStepRecord.approval_case_id == case.id)
                    .order_by(ApprovalStepRecord.step_no)
                ).scalars()
            )
            assert [(item.step_no, item.step_name, item.status) for item in steps] == [
                (1, "申请", "completed"),
                (2, "受理", "completed"),
                (3, "审核", "completed"),
                (4, "备案", "completed"),
            ]
            decisions = list(
                session.execute(
                    select(ApprovalDecisionRecord).where(ApprovalDecisionRecord.step_id.in_([item.id for item in steps]))
                ).scalars()
            )
            assert [item.decision for item in decisions] == ["approved", "approved", "approved", "approved"]

            delivery = session.execute(
                select(DeliveryTaskRecord).where(DeliveryTaskRecord.tenant_id == "sd-default", DeliveryTaskRecord.delivery_code == apply_id)
            ).scalar_one()
            assert delivery.application_code == apply_id
            assert delivery.state == "granted"
            assert delivery.channel == "table"
            access_grant = delivery.payload_json["access_grant"]
            assert access_grant["authz_id"] == authz_id
            assert access_grant["limit_day"] == 180
            assert access_grant["status"] == 0
            assert access_grant["apply_status"] == 9
            assert access_grant["res_type"] == "table"
            assert session.execute(
                select(DeliverySubscriptionRecord).where(
                    DeliverySubscriptionRecord.tenant_id == "sd-default",
                    DeliverySubscriptionRecord.delivery_code == apply_id,
                )
            ).scalar_one_or_none() is None

            catalog = session.execute(
                select(CatalogEntryRecord).where(CatalogEntryRecord.tenant_id == "sd-default", CatalogEntryRecord.catalog_code == catalog_code)
            ).scalar_one()
            assert catalog.title == "停车场信息"
            assert catalog.lifecycle_status == "active"
            items = list(
                session.execute(
                    select(CatalogItemRecord)
                    .where(CatalogItemRecord.tenant_id == "sd-default", CatalogItemRecord.catalog_code == catalog_code)
                    .order_by(CatalogItemRecord.display_order, CatalogItemRecord.item_code)
                ).scalars()
            )
            assert {item.item_code: item.title for item in items} == {name_item: "名称", address_item: "地址"}
            assert {item.item_code: item.summary_json.get("sensitive_level") for item in items} == {name_item: "1", address_item: ""}

            asset = session.execute(
                select(ResourceAssetRecord).where(ResourceAssetRecord.tenant_id == "sd-default", ResourceAssetRecord.resource_code == resource_id)
            ).scalar_one()
            assert asset.title == "停车场信息_库表资源"
            assert asset.resource_kind == "table"
            assert asset.lifecycle_status == "suspended"
            assert asset.catalog_code == catalog_code
            assert asset.access_policy_json["share_type"] == 2
            assert asset.access_policy_json["open_type"] == 2

            schema_mappings = list(
                session.execute(
                    select(ResourceSchemaMappingRecord)
                    .where(ResourceSchemaMappingRecord.tenant_id == "sd-default", ResourceSchemaMappingRecord.resource_code == resource_id)
                    .order_by(ResourceSchemaMappingRecord.mapping_code)
                ).scalars()
            )
            assert {item.mapping_code for item in schema_mappings} == {name_mapping, address_mapping}
            assert {item.catalog_item_code for item in schema_mappings} == {name_item, address_item}
            assert {item.source_schema_ref["column"] for item in schema_mappings} == {"name", "address"}
            assert {item.status for item in schema_mappings} == {"active"}

            industry_assets = list(
                session.execute(
                    select(ResourceAssetRecord).where(
                        ResourceAssetRecord.tenant_id == "sd-default",
                        ResourceAssetRecord.resource_code.in_([industry_table_resource_id, industry_file_resource_id, industry_url_resource_id]),
                    )
                ).scalars()
            )
            assert {item.resource_code: item.resource_kind for item in industry_assets} == {
                industry_table_resource_id: "table",
                industry_file_resource_id: "file",
                industry_url_resource_id: "url",
            }
            assert {item.catalog_code for item in industry_assets} == {industry_catalog_code}
            industry_bindings = list(
                session.execute(
                    select(ResourceChannelBindingRecord).where(
                        ResourceChannelBindingRecord.tenant_id == "sd-default",
                        ResourceChannelBindingRecord.resource_code.in_([industry_table_resource_id, industry_file_resource_id, industry_url_resource_id]),
                    )
                ).scalars()
            )
            assert {item.channel_kind for item in industry_bindings} >= {"table", "file", "url"}
            assert industry_file_binding in {item.binding_code for item in industry_bindings}
            assert industry_table_binding in {item.binding_code for item in industry_bindings}
            industry_mappings = list(
                session.execute(
                    select(ResourceSchemaMappingRecord).where(
                        ResourceSchemaMappingRecord.tenant_id == "sd-default",
                        ResourceSchemaMappingRecord.resource_code == industry_table_resource_id,
                    )
                ).scalars()
            )
            assert len(industry_mappings) >= 7
            assert {item.status for item in industry_mappings} == {"active"}
            industry_snapshots = list(
                session.execute(
                    select(ResourceSchemaSnapshotRecord).where(
                        ResourceSchemaSnapshotRecord.tenant_id == "sd-default",
                        ResourceSchemaSnapshotRecord.resource_code.in_([industry_table_binding, industry_table_resource_id]),
                    )
                ).scalars()
            )
            assert any(item.source_ref and ":db_meta_column:" in item.source_ref for item in industry_snapshots)
            assert session.execute(
                select(ApprovalCaseRecord).where(
                    ApprovalCaseRecord.tenant_id == "sd-default",
                    ApprovalCaseRecord.application_code == f"resource-review:{industry_table_resource_id}",
                )
            ).scalar_one_or_none() is not None
            assert session.execute(
                select(DeliveryAttemptRecord).where(
                    DeliveryAttemptRecord.tenant_id == "sd-default",
                    DeliveryAttemptRecord.attempt_code == f"materialize:{materialized_catalog_id}:{materialized_resource_id}",
                )
            ).scalar_one_or_none() is not None
            assert session.execute(
                select(DeliveryExecutionEvidenceRecord).where(
                    DeliveryExecutionEvidenceRecord.tenant_id == "sd-default",
                    DeliveryExecutionEvidenceRecord.evidence_ref == f"materialize:{materialized_catalog_id}:{materialized_resource_id}",
                )
            ).scalar_one_or_none() is not None

            coding_asset = session.execute(
                select(ResourceAssetRecord).where(ResourceAssetRecord.tenant_id == "sd-default", ResourceAssetRecord.resource_code == coding_resource_id)
            ).scalar_one()
            assert coding_asset.catalog_code == coding_catalog_code
            coding_mappings = list(
                session.execute(
                    select(ResourceSchemaMappingRecord).where(
                        ResourceSchemaMappingRecord.tenant_id == "sd-default",
                        ResourceSchemaMappingRecord.resource_code == coding_resource_id,
                    )
                ).scalars()
            )
            assert len(coding_mappings) == 9

            legal_person_catalog = session.execute(
                select(CatalogEntryRecord).where(CatalogEntryRecord.tenant_id == "sd-default", CatalogEntryRecord.catalog_code == legal_person_catalog_code)
            ).scalar_one()
            assert legal_person_catalog.title == "法人登记注册基本信息"
            legal_person_asset = session.execute(
                select(ResourceAssetRecord).where(ResourceAssetRecord.tenant_id == "sd-default", ResourceAssetRecord.resource_code == legal_person_resource_id)
            ).scalar_one()
            assert legal_person_asset.catalog_code == legal_person_catalog_code
            legal_person_topic = session.execute(
                select(TopicPackageRecord).where(TopicPackageRecord.tenant_id == "sd-default", TopicPackageRecord.package_code == legal_person_group_package)
            ).scalar_one()
            assert legal_person_topic.display_snapshot_json["projection_kind"] == "catalog_group"
            legal_person_topic_items = list(
                session.execute(
                    select(TopicPackageItemRecord).where(
                        TopicPackageItemRecord.tenant_id == "sd-default",
                        TopicPackageItemRecord.package_code == legal_person_group_package,
                        TopicPackageItemRecord.ref_type == "catalog_entry",
                    )
                ).scalars()
            )
            assert any(item.ref_id == legal_person_catalog_code for item in legal_person_topic_items)
            legal_person_visibility = list(
                session.execute(
                    select(TopicPackageVisibilityRecord).where(
                        TopicPackageVisibilityRecord.tenant_id == "sd-default",
                        TopicPackageVisibilityRecord.package_code == legal_person_group_package,
                    )
                ).scalars()
            )
            assert len(legal_person_visibility) == 18
            assert {item.policy_status for item in legal_person_visibility} == {"approved"}

            from zw_brain.command.brain import BrainService
            from zw_brain.shared import audit as audit_bus
            from zw_brain.shared.database_store import DatabaseStore
            from zw_brain.shared.state_store import StateStore

            database_store = DatabaseStore()
            audit_bus.configure_sink(database_store.append_audit_event)
            service = BrainService(state_store=StateStore(database_store=database_store))

            topic_detail = service.invoke_skill(
                "topic.package.query",
                {"package_code": legal_person_group_package, "role": "r7"},
            )["items"][0]
            assert topic_detail["projectionKind"] == "catalog_group"
            assert topic_detail["projectionStatus"] == "projected"
            assert topic_detail["visibleOrgCount"] == 18
            assert topic_detail["activeCatalogCount"] >= 1
            assert topic_detail["hiddenCatalogCount"] >= 1
            assert "inactive_catalog_item_hidden" in topic_detail["projectionFailureReasons"]
            assert "authorization_not_effective" in topic_detail["projectionFailureReasons"]
            assert topic_detail["sourceFact"].startswith("share_zone/share_group legacy tables are empty")
            assert topic_detail["applicationBoundary"]["visibilitySource"] == ["data_group_permission"]
            assert topic_detail["applicationBoundary"]["approvedViewPolicyCount"] == 18
            assert any(item["catalog_code"] == legal_person_catalog_code and item["visible"] for item in topic_detail["catalogProjectionItems"])

            share_zones = service.invoke_skill("catalog.share_zone.query", {"role": "r7"})
            assert share_zones["source_fact"].startswith("legacy share_zone/share_group dump rows are empty")
            assert any(item["package_code"] == legal_person_group_package for item in share_zones["items"])

            discovered = service.invoke_skill("data.search", {"query": "法人登记注册基本信息", "role": "r7"})
            discovered_item = next(item for item in discovered["results"] if item["id"] == legal_person_catalog_code)
            assert discovered_item["status"] == "active"
            assert discovered_item["topicProjections"][0]["projectionStatus"] == "projected"
            assert discovered_item["topicProjections"][0]["visibleOrgCount"] == 18

            database_store.catalog_repo.upsert_from_resource(
                {
                    "id": "F4-INVISIBLE-CATALOG",
                    "name": "F4 active but invisible catalog",
                    "status": "active",
                    "provider": "ORG-F4",
                    "summary_json": {"description": "active catalog without approved visibility"},
                }
            )
            database_store.topic_package_repo.create_package(
                {
                    "package_code": "catalog-group:f4-invisible",
                    "title": "F4 invisible projection",
                    "status": "published",
                    "display_snapshot_json": {"projection_kind": "catalog_group", "source": "synthetic-canonical-negative"},
                }
            )
            database_store.topic_package_repo.configure_package(
                "catalog-group:f4-invisible",
                {
                    "items": [
                        {
                            "item_code": "catalog:F4-INVISIBLE-CATALOG",
                            "ref_type": "catalog_entry",
                            "ref_id": "F4-INVISIBLE-CATALOG",
                            "title": "F4 active but invisible catalog",
                        }
                    ],
                    "visibility": [
                        {
                            "visibility_code": "f4-pending-visibility",
                            "org_code": "ORG-F4",
                            "surface": "webui",
                            "intent": "view",
                            "policy_status": "pending_review",
                            "condition_json": {"source": "canonical-negative-test"},
                        }
                    ],
                },
            )
            invisible_topic = service.invoke_skill(
                "topic.package.query",
                {"package_code": "catalog-group:f4-invisible", "role": "r7"},
            )["items"][0]
            assert invisible_topic["projectionStatus"] == "blocked"
            assert "no_approved_visibility" in invisible_topic["projectionFailureReasons"]
            assert "authorization_not_effective" in invisible_topic["projectionFailureReasons"]
            assert not any(item["id"] == "F4-INVISIBLE-CATALOG" for item in service.invoke_skill("data.search", {"query": "F4 active", "role": "r7"})["results"])

            database_store.catalog_repo.upsert_from_resource(
                {
                    "id": "F4-INACTIVE-CATALOG",
                    "name": "F4 inactive catalog",
                    "status": "draft",
                    "provider": "ORG-F4",
                    "summary_json": {"description": "inactive catalog hidden from projection"},
                }
            )
            database_store.topic_package_repo.create_package(
                {
                    "package_code": "catalog-group:f4-inactive",
                    "title": "F4 inactive projection",
                    "status": "published",
                    "display_snapshot_json": {"projection_kind": "catalog_group", "source": "synthetic-canonical-negative"},
                }
            )
            database_store.topic_package_repo.configure_package(
                "catalog-group:f4-inactive",
                {
                    "items": [
                        {
                            "item_code": "catalog:F4-INACTIVE-CATALOG",
                            "ref_type": "catalog_entry",
                            "ref_id": "F4-INACTIVE-CATALOG",
                            "title": "F4 inactive catalog",
                        }
                    ],
                    "visibility": [
                        {
                            "visibility_code": "f4-approved-visibility-inactive",
                            "org_code": "ORG-F4",
                            "surface": "webui",
                            "intent": "view",
                            "policy_status": "approved",
                            "condition_json": {"source": "canonical-negative-test"},
                        }
                    ],
                },
            )
            inactive_topic = service.invoke_skill(
                "topic.package.query",
                {"package_code": "catalog-group:f4-inactive", "role": "r7"},
            )["items"][0]
            assert inactive_topic["projectionStatus"] == "blocked"
            assert "no_active_catalog_item" in inactive_topic["projectionFailureReasons"]
            assert inactive_topic["catalogProjectionItems"][0]["hidden_reason"] == "catalog_not_active"

            database_store.catalog_repo.upsert_from_resource(
                {
                    "id": "F4-HIDDEN-FIELDS",
                    "name": "F4 hidden fields catalog",
                    "status": "active",
                    "provider": "ORG-F4",
                    "summary_json": {"description": "active catalog without visible fields"},
                }
            )
            database_store.resource_api_repo.upsert_asset(
                {
                    "resource_code": "F4-HIDDEN-FIELDS-RESOURCE",
                    "title": "F4 hidden fields resource",
                    "resource_kind": "table",
                    "lifecycle_status": "active",
                    "catalog_code": "F4-HIDDEN-FIELDS",
                    "source_ref": "canonical-negative-test:resource:F4-HIDDEN-FIELDS-RESOURCE",
                }
            )
            database_store.topic_package_repo.create_package(
                {
                    "package_code": "catalog-group:f4-hidden-fields",
                    "title": "F4 hidden fields projection",
                    "status": "published",
                    "display_snapshot_json": {"projection_kind": "catalog_group", "source": "synthetic-canonical-negative"},
                }
            )
            database_store.topic_package_repo.configure_package(
                "catalog-group:f4-hidden-fields",
                {
                    "items": [
                        {
                            "item_code": "catalog:F4-HIDDEN-FIELDS",
                            "ref_type": "catalog_entry",
                            "ref_id": "F4-HIDDEN-FIELDS",
                            "title": "F4 hidden fields catalog",
                        }
                    ],
                    "visibility": [
                        {
                            "visibility_code": "f4-approved-visibility-hidden-fields",
                            "org_code": "ORG-F4",
                            "surface": "webui",
                            "intent": "view",
                            "policy_status": "approved",
                            "condition_json": {"source": "canonical-negative-test"},
                        }
                    ],
                },
            )
            hidden_topic = service.invoke_skill(
                "topic.package.query",
                {"package_code": "catalog-group:f4-hidden-fields", "role": "r7"},
            )["items"][0]
            assert hidden_topic["projectionStatus"] == "blocked"
            assert "resource_binding_has_no_visible_fields" in hidden_topic["projectionFailureReasons"]
            assert "resource_attached_but_no_visible_fields" in hidden_topic["projectionFailureReasons"]
            assert hidden_topic["catalogProjectionItems"][0]["resource_count"] == 1
            assert hidden_topic["catalogProjectionItems"][0]["hidden_reason"] == "resource_binding_has_no_visible_fields"

            refs: dict[str, set[str]] = {}
            for item in session.execute(
                select(LegacyObjectMappingRecord).where(
                    LegacyObjectMappingRecord.tenant_id == "sd-default",
                    LegacyObjectMappingRecord.legacy_object_ref.in_(
                        [
                            apply_id,
                            authz_id,
                            catalog_id,
                            resource_id,
                            name_item,
                            address_item,
                            name_mapping,
                            address_mapping,
                            industry_catalog_id,
                            industry_table_resource_id,
                            industry_file_resource_id,
                            industry_url_resource_id,
                            industry_table_binding,
                            industry_file_binding,
                            coding_catalog_id,
                            coding_resource_id,
                            legal_person_catalog_id,
                            legal_person_resource_id,
                            legal_person_group_id,
                            *course_ids,
                        ]
                    ),
                )
            ).scalars():
                refs.setdefault(item.legacy_object_ref, set()).add(item.canonical_type)
            assert refs[apply_id] >= {"application_record", "DeliveryTaskRecord"}
            assert refs[authz_id] == {"DeliveryTaskRecord"}
            assert refs[catalog_id] == {"catalog_entry"}
            assert refs[resource_id] == {"resource_asset"}
            assert refs[name_item] == {"catalog_item"}
            assert refs[address_item] == {"catalog_item"}
            assert refs[name_mapping] == {"resource_schema_mapping"}
            assert refs[address_mapping] == {"resource_schema_mapping"}
            assert refs[industry_catalog_id] == {"catalog_entry"}
            assert refs[industry_table_resource_id] >= {"resource_asset"}
            assert refs[industry_file_resource_id] >= {"resource_asset"}
            assert refs[industry_url_resource_id] == {"resource_asset"}
            assert refs[industry_table_binding] >= {"resource_channel_binding"}
            assert refs[industry_file_binding] >= {"resource_channel_binding"}
            assert refs[coding_catalog_id] == {"catalog_entry"}
            assert refs[coding_resource_id] == {"resource_asset"}
            assert refs[legal_person_catalog_id] == {"catalog_entry"}
            assert refs[legal_person_resource_id] >= {"resource_asset", "resource_channel_binding", "resource_schema_snapshot"}
            assert refs[legal_person_group_id] >= {"TopicPackageRecord", "catalog_entry"}
            for course_id in course_ids:
                assert refs[course_id] == {"approval_step", "approval_decision"}


def test_legacy_service_sql_never_enters_canonical_bindings() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        dumps_dir = root / "dumps"
        db_path = root / "customer.db"
        _write_core_dumps(dumps_dir)
        (dumps_dir / "dump-dsp_service-202604000000.sql").write_text(
            dedent(
                """
                DROP TABLE IF EXISTS `api_service_info`;
                CREATE TABLE `api_service_info` (
                  `ID` varchar(36),
                  `NAME` varchar(128),
                  `IS_PUBLIC` varchar(4),
                  PRIMARY KEY (`ID`)
                ) ENGINE=InnoDB;
                INSERT INTO `api_service_info` VALUES ('svc-1','人口查询 API','1');
                DROP TABLE IF EXISTS `api_service_data`;
                CREATE TABLE `api_service_data` (
                  `API_ID` varchar(36),
                  `SERVICE_ID` varchar(36),
                  `SERVICE_SQL` text,
                  `RULE_PARAM` text,
                  `RULE_STR` text,
                  PRIMARY KEY (`API_ID`)
                ) ENGINE=InnoDB;
                INSERT INTO `api_service_data` VALUES ('data-1','svc-1','select name, id_card from citizen','{"id":"string"}','公开字段');
                """
            ).strip(),
            encoding="utf-8",
        )
        report = run_migration(MigrationOptions(dumps_dir=dumps_dir, db_path=db_path, reset_db=True, strict=True))
        assert report["status"] == "succeeded"

        from zw_brain.domain.repositories.resource_api import ResourceApiRepository

        binding = ResourceApiRepository().get_binding("svc-1:data:data-1")
        assert binding is not None
        assert binding.schema_ref == {"rule_param": '{"id":"string"}', "rule_str": "公开字段"}
        assert "SERVICE_SQL" not in json.dumps(binding.schema_ref, ensure_ascii=False)
        assert "select name" not in json.dumps(binding.schema_ref, ensure_ascii=False)


def test_legacy_acceptance_fail_closed_missing_dump_without_apply() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        dumps_dir = root / "dumps"
        _write_core_dumps(dumps_dir)
        (dumps_dir / "dump-dsp_connect-202604000000.sql").unlink()
        with pytest.raises(MigrationError) as exc_info:
            run_acceptance_migration(MigrationOptions(dumps_dir=dumps_dir, db_path=root / "customer.db", strict=True))
        report = exc_info.value.report
        assert report["status"] == "failed"
        assert report["stages"]["dry_run"]["status"] == "failed"
        assert report["stages"]["apply"] == {"stage": "apply", "status": "skipped", "reason": "dry_run_failed", "errors": ["dry_run_failed"]}
        assert "dsp_connect" in report["stages"]["dry_run"]["fail_closed"]["missing_dumps"]


def test_legacy_migration_strict_rejects_duplicate_required_dumps() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        dumps_dir = root / "dumps"
        _write_core_dumps(dumps_dir)
        (dumps_dir / "dump-dsp_catalog-202604000001.sql").write_text((dumps_dir / "dump-dsp_catalog-202604000000.sql").read_text(encoding="utf-8"), encoding="utf-8")
        with pytest.raises(MigrationError) as exc_info:
            run_migration(MigrationOptions(dumps_dir=dumps_dir, db_path=root / "customer.db", reset_db=True, strict=True))
        assert "duplicate required dump(s): dsp_catalog" in exc_info.value.report["errors"]


def test_legacy_migration_strict_rejects_unmapped_source_tables() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        dumps_dir = root / "dumps"
        _write_core_dumps(dumps_dir)
        with (dumps_dir / "dump-dsp_catalog-202604000000.sql").open("a", encoding="utf-8") as fh:
            fh.write(
                dedent(
                    """
                    DROP TABLE IF EXISTS `unknown_business_table`;
                    CREATE TABLE `unknown_business_table` (
                      `id` varchar(36),
                      PRIMARY KEY (`id`)
                    ) ENGINE=InnoDB;
                    INSERT INTO `unknown_business_table` VALUES ('row-1');
                    """
                )
            )
        with pytest.raises(MigrationError) as exc_info:
            run_migration(MigrationOptions(dumps_dir=dumps_dir, db_path=root / "customer.db", reset_db=True, strict=True))
        assert any("unknown source row table(s)" in item and "dsp_catalog.unknown_business_table" in item for item in exc_info.value.report["errors"])



def test_legacy_migration_strict_rejects_unaccounted_handled_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    from zw_brain.adapters.legacy._common import ImportStats
    from zw_brain.adapters.legacy.runner import LegacyImportRunner

    original_mappers_for = LegacyImportRunner.mappers_for
    original_import_schema = LegacyImportRunner.import_schema

    class FakeCatalogMapper:
        HANDLED_TABLES = {"data_catalog"}

    def fake_mappers_for(self: LegacyImportRunner, schema: str) -> list[object]:
        if schema == "dsp_catalog":
            return [FakeCatalogMapper()]
        return original_mappers_for(self, schema)

    def fake_import_schema(self: LegacyImportRunner, schema: str) -> list[object] | object | None:
        if schema == "dsp_catalog":
            return ImportStats(schema=schema, dump_path=self.cache_dir / "fake.sql")
        return original_import_schema(self, schema)

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        dumps_dir = root / "dumps"
        _write_core_dumps(dumps_dir)
        monkeypatch.setattr(LegacyImportRunner, "mappers_for", fake_mappers_for)
        monkeypatch.setattr(LegacyImportRunner, "import_schema", fake_import_schema)
        with pytest.raises(MigrationError) as exc_info:
            run_migration(MigrationOptions(dumps_dir=dumps_dir, db_path=root / "customer.db", reset_db=True, strict=True))
        assert any("unaccounted source row table(s) in declared mapper" in item and "dsp_catalog.data_catalog" in item for item in exc_info.value.report["errors"])
