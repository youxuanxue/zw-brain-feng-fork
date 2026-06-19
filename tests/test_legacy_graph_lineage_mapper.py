"""F3 turn 3: GraphLineageMapper graphdb_* → LineageRelationProjectionRecord mapping.

Real dump scope:
  `old/10示例数据/dump-dsp_metaresource-202604271411.sql` 包含 62 张表的 CREATE TABLE，
  其中 5 张 graphdb_* 表在客户脱敏 dump 中没有 INSERT 行（图血缘尚未启用）。

  本测试因此用 inline 合成 dump 验证 mapping path —— 合成数据严格 mirror dump 的
  CREATE TABLE 列名（参考 old/12-datastructure/dsp_metaresource.xml），仅 INSERT 是
  最小现实样本。这是 D11「不 mock 业务数据」的合理例外：实际 dump 该子集为空。

Coverage:
  - happy: graphdb_node 2 行 + graphdb_node_column 2 行 + graphdb_relation 1 行 →
    1 LineageRelationProjectionRecord 落地，含 start/end node embedded
  - legacy mapping 写入验证（D4 审计可追溯）
  - NULL relation.id fail-closed 验证（R-017 教训）
"""
from __future__ import annotations

from pathlib import Path

import pytest

from zw_brain.adapters.legacy.mappers.graph_lineage import GraphLineageMapper
from zw_brain.domain.repositories.legacy_mapping import LegacyObjectMappingRepository
from zw_brain.domain.repositories.metadata_evidence import MetadataEvidenceRepository
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.migrate import ensure_runtime_schema


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    ensure_runtime_schema()
    DatabaseStore()
    return tmp_path


def _write_dump(tmp_path: Path, *, with_relation: bool = True, broken_relation: bool = False) -> Path:
    """合成 mysqldump 文本，mirror old/12-datastructure/dsp_metaresource.xml graphdb_* schema。"""
    parts: list[str] = [
        "CREATE TABLE `graphdb_node` (",
        "  `id` varchar(64) NOT NULL,",
        "  `database_id` varchar(64) DEFAULT NULL,",
        "  `node_name_cn` varchar(255) DEFAULT NULL,",
        "  `node_name` varchar(255) DEFAULT NULL,",
        "  `node_desc` text,",
        "  `meta_id` varchar(64) DEFAULT NULL,",
        "  `source_table_meta_id` varchar(64) DEFAULT NULL,",
        "  `source_database_meta_id` varchar(64) DEFAULT NULL,",
        "  `status` varchar(16) DEFAULT NULL,",
        "  PRIMARY KEY (`id`)",
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;",
        "INSERT INTO `graphdb_node` VALUES "
        "('NODE-USER','DB-1','用户表','user','人口主题节点 user 表','META-T-USER','RES-USER','DB-META-1','active'),"
        "('NODE-ORDER','DB-1','订单表','order','人口主题节点 order 表','META-T-ORDER','RES-ORDER','DB-META-1','active');",

        "CREATE TABLE `graphdb_node_column` (",
        "  `id` varchar(64) NOT NULL,",
        "  `node_id` varchar(64) DEFAULT NULL,",
        "  `column_name_en` varchar(64) DEFAULT NULL,",
        "  `column_name` varchar(255) DEFAULT NULL,",
        "  `column_type` varchar(32) DEFAULT NULL,",
        "  `source_column_meta_id` varchar(64) DEFAULT NULL,",
        "  `order_id` int DEFAULT '0',",
        "  `table_column_name` varchar(255) DEFAULT NULL,",
        "  PRIMARY KEY (`id`)",
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;",
        "INSERT INTO `graphdb_node_column` VALUES "
        "('COL-USER-ID','NODE-USER','id','用户ID','VARCHAR','META-COL-1',1,'user.id'),"
        "('COL-ORDER-USER','NODE-ORDER','user_id','下单用户ID','VARCHAR','META-COL-2',2,'order.user_id');",

        "CREATE TABLE `graphdb_relation` (",
        "  `id` varchar(64) NOT NULL,",
        "  `database_id` varchar(64) DEFAULT NULL,",
        "  `relation_name` varchar(255) DEFAULT NULL,",
        "  `start_node_id` varchar(64) DEFAULT NULL,",
        "  `end_node_id` varchar(64) DEFAULT NULL,",
        "  `relation_attr` text,",
        "  `status` varchar(16) DEFAULT NULL,",
        "  `create_time` datetime DEFAULT NULL,",
        "  PRIMARY KEY (`id`)",
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;",
    ]
    if with_relation and not broken_relation:
        parts.append(
            "INSERT INTO `graphdb_relation` VALUES "
            "('REL-USER-ORDER','DB-1','用户下单关系','NODE-USER','NODE-ORDER','user.id = order.user_id','active','2026-02-01 10:00:00');"
        )
    elif with_relation and broken_relation:
        parts.append(
            "INSERT INTO `graphdb_relation` VALUES "
            "(NULL,'DB-1','缺主键关系','NODE-USER','NODE-ORDER','x','active','2026-02-01 10:00:00');"
        )

    parts += [
        "CREATE TABLE `graphdb_relation_attr` (",
        "  `id` varchar(64) NOT NULL,",
        "  `relation_id` varchar(64) DEFAULT NULL,",
        "  `relate_condition` varchar(255) DEFAULT NULL,",
        "  `start_node_code` varchar(64) DEFAULT NULL,",
        "  `start_node_name` varchar(255) DEFAULT NULL,",
        "  `relation_attr_operator` varchar(16) DEFAULT NULL,",
        "  `end_node_code` varchar(64) DEFAULT NULL,",
        "  `end_node_name` varchar(255) DEFAULT NULL,",
        "  PRIMARY KEY (`id`)",
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;",
        "INSERT INTO `graphdb_relation_attr` VALUES "
        "('ATTR-1','REL-USER-ORDER','user.id = order.user_id','user','用户','=','order','订单');",

        "CREATE TABLE `graphdb_relation_column` (",
        "  `id` varchar(64) NOT NULL,",
        "  `relation_id` varchar(64) DEFAULT NULL,",
        "  `column_name` varchar(64) DEFAULT NULL,",
        "  `column_type` varchar(32) DEFAULT NULL,",
        "  PRIMARY KEY (`id`)",
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;",
        "INSERT INTO `graphdb_relation_column` VALUES "
        "('RC-1','REL-USER-ORDER','user_id','VARCHAR');",
    ]

    dump = tmp_path / "dump-dsp_metaresource-202604271411.sql"
    dump.write_text("\n".join(parts), encoding="utf-8")
    return dump


def test_graph_lineage_happy_path_creates_lineage_relation(temp_db: Path, tmp_path: Path) -> None:
    """graphdb_relation 1 行 + 2 nodes + 2 columns + 1 attr + 1 rel-col → 1 LineageRelationProjectionRecord 落地。"""
    dump_path = _write_dump(tmp_path)
    mapper = GraphLineageMapper(tenant_id="sd-default")

    stats = mapper.import_dump(dump_path)

    assert stats.counts.get("graphdb_relation.imported", 0) == 1
    assert stats.counts.get("graphdb_node.buffered", 0) == 2
    assert stats.counts.get("graphdb_node_column.buffered", 0) == 2
    assert stats.counts.get("graphdb_relation_attr.buffered", 0) == 1
    assert stats.counts.get("graphdb_relation_column.buffered", 0) == 1
    assert stats.counts.get("graphdb_relation.errors", 0) == 0

    repo = MetadataEvidenceRepository()
    relations = repo.list_lineage_relations(tenant_id="sd-default", relation_scope="graphdb")
    assert len(relations) == 1
    rel = relations[0]
    assert rel.relation_ref == "graphdb:REL-USER-ORDER"
    assert rel.relation_scope == "graphdb"
    assert rel.relation_type == "用户下单关系"
    assert rel.source_resource_code == "RES-USER"
    assert rel.target_resource_code == "RES-ORDER"
    assert rel.source_schema_ref == "user"
    assert rel.target_schema_ref == "order"

    rule = rel.relation_rule_json
    assert rule["relation_id"] == "REL-USER-ORDER"
    assert rule["relation_name"] == "用户下单关系"
    # start_node 嵌入 columns
    assert rule["start_node"]["node_name"] == "user"
    assert rule["start_node"]["node_name_cn"] == "用户表"
    assert len(rule["start_node"]["columns"]) == 1
    assert rule["start_node"]["columns"][0]["column_name_en"] == "id"
    # end_node 嵌入 columns
    assert rule["end_node"]["node_name"] == "order"
    assert len(rule["end_node"]["columns"]) == 1
    # attrs 嵌入
    assert len(rule["attrs"]) == 1
    assert rule["attrs"][0]["relate_condition"] == "user.id = order.user_id"
    # columns 嵌入
    assert len(rule["columns"]) == 1
    assert rule["columns"][0]["column_name"] == "user_id"


def test_graph_lineage_legacy_mapping_record_written(temp_db: Path, tmp_path: Path) -> None:
    """每个迁入 graphdb_relation → 1 条 LegacyObjectMappingRecord（upsert_lineage_relation 内部已写入）。"""
    dump_path = _write_dump(tmp_path)
    mapper = GraphLineageMapper(tenant_id="sd-default")
    mapper.import_dump(dump_path)

    repo = LegacyObjectMappingRepository()
    mappings = repo.list_mappings(tenant_id="sd-default", canonical_type="lineage_relation_projection")
    refs = {m.canonical_ref for m in mappings}
    assert "graphdb:REL-USER-ORDER" in refs


def test_graph_lineage_missing_id_fail_closed(temp_db: Path, tmp_path: Path) -> None:
    """graphdb_relation 行缺主键 → ValueError → stats.errors > 0（R-017 fail-closed）。"""
    dump_path = _write_dump(tmp_path, broken_relation=True)
    mapper = GraphLineageMapper(tenant_id="sd-default")

    stats = mapper.import_dump(dump_path)
    # Source row counted (read from dump) — error is in mapping step
    assert stats.source_counts.get("graphdb_relation") == 1
    # Error path: bump('graphdb_relation', 'errors') + stats.skipped key
    assert stats.counts.get("graphdb_relation.errors", 0) == 1
    # No silent collision: no relation written
    repo = MetadataEvidenceRepository()
    relations = repo.list_lineage_relations(tenant_id="sd-default", relation_scope="graphdb")
    assert len(relations) == 0
