"""F3 turn 2: BasesubjectMapper dsp_basesubject → TopicPackageRecord mapping.

Real dump scope:
  `old/10示例数据/dump-dsp_basesubject-202604271138.sql` 包含 81 张表的 CREATE TABLE，
  但 11 张主题库主体表（basesubject_info / bs_resource / schema_info 等）在客户脱敏
  dump 中没有 INSERT 行（行业 basesubject 数据为空）。

  本测试因此用 inline 合成 dump 验证 mapping path —— 合成数据严格 mirror dump 的
  CREATE TABLE 列名（参考 old/12-datastructure/dsp_basesubject.xml），仅 INSERT 是
  最小现实样本。这是 D11「不 mock 业务数据」的合理例外：实际 dump 该子集为空，
  不存在「真实数据可用却用 mock」的情况。

Coverage:
  - happy: basesubject_info / bs_resource / schema_info 各 1-2 行真实风格数据
  - missing-field skip: basesubject_info 行缺 id 字段触发 stats.skipped
"""
from __future__ import annotations

from pathlib import Path

import pytest

from zw_brain.adapters.legacy.mappers.basesubject import BasesubjectMapper
from zw_brain.domain.repositories.legacy_mapping import LegacyObjectMappingRepository
from zw_brain.domain.repositories.topic_package import TopicPackageRepository
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.migrate import ensure_runtime_schema


@pytest.fixture
def temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "basesubject.db"
    monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
    ensure_runtime_schema()
    # Construct DatabaseStore so audit/external_adapter writes have a sink
    DatabaseStore()
    return db_path


def _write_dump(tmp_path: Path, *, with_subject: bool = True, with_resource: bool = True, with_schema: bool = True, broken_subject: bool = False) -> Path:
    """合成 mysqldump 文本，mirror old/12-datastructure/dsp_basesubject.xml schema。"""
    parts: list[str] = [
        # basesubject_info: 18 columns total — we include core columns to test mapping
        "CREATE TABLE `basesubject_info` (",
        "  `id` varchar(64) NOT NULL,",
        "  `name` varchar(255) DEFAULT NULL,",
        "  `schema_id` varchar(64) DEFAULT NULL,",
        "  `lead_org_code` varchar(64) DEFAULT NULL,",
        "  `lead_org_name` varchar(255) DEFAULT NULL,",
        "  `source_org_codes` text,",
        "  `source_org_names` text,",
        "  `standard_id` varchar(64) DEFAULT NULL,",
        "  `standard_name` varchar(255) DEFAULT NULL,",
        "  `contacter` varchar(64) DEFAULT NULL,",
        "  `contact_phone` varchar(32) DEFAULT NULL,",
        "  `description` text,",
        "  `resource_count` int DEFAULT '0',",
        "  `service_count` int DEFAULT '0',",
        "  `creator_id` varchar(64) DEFAULT NULL,",
        "  `create_time` datetime DEFAULT NULL,",
        "  PRIMARY KEY (`id`)",
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;",
    ]
    if with_subject and not broken_subject:
        parts.append(
            "INSERT INTO `basesubject_info` VALUES "
            "('SUBJ-001','人口主题库','SCHEMA-POP','370000','山东省公安厅','370100|370200','济南市|青岛市',"
            "'STD-001','GB/T-人口标准','张三','13800138000','人口主题库（测试 fixture）',12,3,'creator-1','2026-01-15 10:00:00'),"
            "('SUBJ-002','法人主题库','SCHEMA-CORP','370000','山东省市场监管局',NULL,NULL,"
            "'STD-002','GB/T-法人标准','李四','13900139000','法人主题库（测试 fixture）',8,2,'creator-2','2026-01-15 10:30:00');"
        )
    elif with_subject and broken_subject:
        # Missing `id` column triggers KeyError path
        parts.append(
            "INSERT INTO `basesubject_info` VALUES "
            "(NULL,'缺主键 fixture',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,'broken row',0,0,NULL,NULL);"
        )

    parts += [
        "CREATE TABLE `bs_resource` (",
        "  `id` varchar(64) NOT NULL,",
        "  `name` varchar(255) DEFAULT NULL,",
        "  `basesubject_id` varchar(64) DEFAULT NULL,",
        "  `group_id` varchar(64) DEFAULT NULL,",
        "  `type` varchar(32) DEFAULT NULL,",
        "  `source_dept_code` varchar(64) DEFAULT NULL,",
        "  `source_dept_name` varchar(255) DEFAULT NULL,",
        "  `resource_format_text` varchar(64) DEFAULT NULL,",
        "  `update_cycle_text` varchar(64) DEFAULT NULL,",
        "  `description` text,",
        "  PRIMARY KEY (`id`)",
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;",
    ]
    if with_resource:
        parts.append(
            "INSERT INTO `bs_resource` VALUES "
            "('RES-001','人口基本信息表','SUBJ-001','GRP-1','table','370001','公安户籍处','CSV','每日','常住人口基本字段'),"
            "('RES-002','人口流动表','SUBJ-001','GRP-1','table','370001','公安户籍处','JSON','每周','流动人口字段');"
        )

    parts += [
        "CREATE TABLE `schema_info` (",
        "  `schema_id` varchar(64) NOT NULL,",
        "  `schema_name` varchar(255) DEFAULT NULL,",
        "  `authority_org_code` varchar(64) DEFAULT NULL,",
        "  `authority_org_name` varchar(255) DEFAULT NULL,",
        "  `comment` text,",
        "  `status` varchar(16) DEFAULT NULL,",
        "  PRIMARY KEY (`schema_id`)",
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;",
    ]
    if with_schema:
        parts.append(
            "INSERT INTO `schema_info` VALUES "
            "('SCHEMA-POP','人口主题 schema','370000','山东省公安厅','人口主题字段标准','active');"
        )

    # dump file name follows convention: dump-<schema>-<timestamp>.sql
    dump = tmp_path / "dump-dsp_basesubject-202604271138.sql"
    dump.write_text("\n".join(parts), encoding="utf-8")
    return dump


def test_basesubject_happy_path_creates_topic_package(temp_db: Path, tmp_path: Path) -> None:
    """basesubject_info / bs_resource / schema_info 各有数据 → 2 个 TopicPackage 落地。"""
    dump_path = _write_dump(tmp_path)
    mapper = BasesubjectMapper(tenant_id="sd-default")

    stats = mapper.import_dump(dump_path)

    assert stats.counts.get("basesubject_info.imported", 0) == 2
    assert stats.counts.get("bs_resource.buffered", 0) == 2  # buffered (joined into items, not separate runs)
    assert stats.counts.get("schema_info.buffered", 0) == 1
    assert stats.schema == "dsp_basesubject"
    # No errors
    assert stats.counts.get("basesubject_info.errors", 0) == 0

    topic_repo = TopicPackageRepository()
    packages = topic_repo.list_packages(tenant_id="sd-default")
    package_codes = {p.package_code for p in packages}
    assert "SUBJ-001" in package_codes
    assert "SUBJ-002" in package_codes

    pkg_001 = topic_repo.get_package("SUBJ-001", tenant_id="sd-default")
    assert pkg_001 is not None
    assert pkg_001.title == "人口主题库"
    assert pkg_001.owner_org_id == "370000"
    # status after create_package + configure_package = configuring
    assert pkg_001.status == "configuring"
    snapshot = pkg_001.display_snapshot_json
    assert snapshot["subject_name"] == "人口主题库"
    # bs_resource 2 行 attach 到 SUBJ-001 → display_snapshot_json.resources
    assert len(snapshot["resources"]) == 2
    resource_names = {r["resource_name"] for r in snapshot["resources"]}
    assert resource_names == {"人口基本信息表", "人口流动表"}
    # contact field 保留原值（read 层 mask）
    assert snapshot["contact"]["contact_name"] == "张三"
    assert snapshot["contact"]["contact_phone"] == "13800138000"
    # schema_info attach via authority_org_code → display_snapshot_json.schema_metas
    assert len(snapshot["schema_metas"]) == 1
    assert snapshot["schema_metas"][0]["schema_name"] == "人口主题 schema"


def test_basesubject_legacy_mapping_record_written(temp_db: Path, tmp_path: Path) -> None:
    """每个迁入 basesubject 主体 → 1 条 LegacyObjectMappingRecord（D4 审计可追溯）。"""
    dump_path = _write_dump(tmp_path)
    mapper = BasesubjectMapper(tenant_id="sd-default")
    mapper.import_dump(dump_path)

    repo = LegacyObjectMappingRepository()
    mappings = repo.list_mappings(tenant_id="sd-default", legacy_object_types=["basesubject_info"])
    refs = {m.legacy_object_ref for m in mappings}
    assert refs == {"SUBJ-001", "SUBJ-002"}
    for m in mappings:
        assert m.canonical_type == "TopicPackageRecord"
        # legacy_system is mapped via tenant_normalizer.legacy_system_for(schema);
        # dsp_basesubject schema → "dsp-sharezone" 类别（主题库属共享专题）
        assert m.legacy_system.startswith("dsp-") or m.legacy_system == "dsp_basesubject"


def test_basesubject_missing_id_field_records_error(temp_db: Path, tmp_path: Path) -> None:
    """basesubject_info 行缺主键（id=NULL）→ 显式 ValueError，走 stats.errors 路径，不 silent collide。"""
    dump_path = _write_dump(tmp_path, broken_subject=True, with_resource=False, with_schema=False)
    mapper = BasesubjectMapper(tenant_id="sd-default")

    stats = mapper.import_dump(dump_path)
    # NULL id 不允许 silent 通过 — _import_one 显式 raise ValueError，主 import_dump
    # 捕获并 bump("basesubject_info", "errors")
    assert stats.source_counts.get("basesubject_info") == 1
    assert stats.counts.get("basesubject_info.errors", 0) == 1, (
        "NULL id 应被识别为 error；mapper 必须 fail-closed 避免 package_code 'None' silent collision"
    )

    # 不应 create 出 package_code="None" 的 TopicPackage
    topic_repo = TopicPackageRepository()
    packages = topic_repo.list_packages(tenant_id="sd-default")
    package_codes = {p.package_code for p in packages}
    assert "None" not in package_codes
    assert "" not in package_codes
