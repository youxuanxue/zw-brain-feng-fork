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
            INSERT INTO `data_catalog` VALUES ('cata-1','人口基本信息','BASE-POP-001','ORG-1','370000','省大数据局','基础人口信息目录','table','1','1',1,'admin','管理员','张三','13800001111',4,'1.0','2025-04-11 11:21:07');
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
            INSERT INTO `data_catalog_column` VALUES ('col-1','cata-1','姓名','varchar',1,'2025-04-11 11:21:07','3','1','name',64);
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
            INSERT INTO `data_resource` VALUES ('res-1','cata-1','RES-POP-001','人口基本信息_库表资源','基础人口表','table','1','admin','管理员','ORG-1','省大数据局','2025-04-01 10:00:00','2025-04-15 10:00:00',4,'1','1','ORG-1','省大数据局','370000');
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
            INSERT INTO `rc_resource` VALUES ('mr-1',1,'停车场信息_库表资源','停车场列表','table','cata-1','人口基本信息','ORG-1','370000','省大数据局',1,1,1,'admin','管理员','2025-04-01 10:00:00','2025-04-15 10:00:00',4);
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
            INSERT INTO `rc_resource_table` VALUES ('bind-1','mr-1','table-1','t_population','db-1','table');
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
            INSERT INTO `rc_resource_catalog_item_link` VALUES ('map-1','cata-1','col-1','mr-1','bind-1','field-name');
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
            INSERT INTO `meta_baseinfo` VALUES ('meta-1','mr-1','人口表','model-1','1','t_population','2025-04-11 11:21:07');
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
        assert report["verification"]["canonical_counts"]["catalog_entry"] >= 1
        assert report["verification"]["canonical_counts"]["resource_schema_mapping"] == 1
        assert report["verification"]["canonical_counts"]["resource_schema_snapshot"] == 1
        assert report["verification"]["canonical_counts"]["metadata_gather_evidence_projection"] == 1
        assert report["verification"]["canonical_counts"]["lineage_relation_projection"] == 1
        assert report["verification"]["canonical_counts"]["quality_evidence_projection"] == 1
        assert not [item for item in report["table_accounting"] if item["unaccounted_rows"]]
        assert "13800001111" not in json.dumps(report, ensure_ascii=False)

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
        assert [item.mapping_code for item in MetadataEvidenceRepository().list_schema_mappings(catalog_code="BASE-POP-001")] == ["map-1"]

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
        assert metadata["total"] == 1
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
        assert any("unmapped source row table(s): dsp_catalog.unknown_business_table" in item for item in exc_info.value.report["errors"])



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
        assert any("unaccounted source row table(s): dsp_catalog.data_catalog" in item for item in exc_info.value.report["errors"])
