from __future__ import annotations

from pathlib import Path

import pytest

from zw_brain.adapters.legacy.mappers.datasource_endpoint import DatasourceEndpointMapper
from zw_brain.domain.repositories.datasource_endpoint import DatasourceEndpointRepository, infer_data_partition
from zw_brain.domain.repositories.metadata_evidence import MetadataEvidenceRepository
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.migrate import ensure_runtime_schema


@pytest.mark.parametrize(
    ("display", "db_name", "node_id", "expected"),
    [
        ("标准服务数据库", "standard-service", None, "standard"),
        ("测试服务库", "test_service", None, "service"),
        ("省公安厅前置库", "test_gat_qzk", None, "front"),
        ("测试节点库", "test1", "node-1", "front"),
    ],
)
def test_infer_data_partition(display: str, db_name: str, node_id: str | None, expected: str) -> None:
    assert infer_data_partition({"display_name": display, "db_name": db_name, "node_id": node_id}) == expected


def _write_meta_database_dump(tmp_path: Path) -> Path:
    dump = tmp_path / "dump-dsp_pipelines-test.sql"
    dump.write_text(
        "\n".join(
            [
                "CREATE TABLE `meta_database` (",
                "  `db_id` varchar(64) NOT NULL,",
                "  `node_id` varchar(64) DEFAULT NULL,",
                "  `node_name` varchar(255) DEFAULT NULL,",
                "  `db_display_name` varchar(255) DEFAULT NULL,",
                "  `db_type` varchar(32) DEFAULT NULL,",
                "  `db_ip` varchar(64) DEFAULT NULL,",
                "  `db_port` int DEFAULT NULL,",
                "  `db_name` varchar(255) DEFAULT NULL,",
                "  `jdbc_type` varchar(255) DEFAULT NULL,",
                "  `db_user` varchar(64) DEFAULT NULL,",
                "  `db_passwd` varchar(255) DEFAULT NULL,",
                "  `jdbc_url` varchar(512) DEFAULT NULL,",
                "  `db_desc` text,",
                "  `db_linkname` varchar(64) DEFAULT NULL,",
                "  `db_linkphone` varchar(32) DEFAULT NULL,",
                "  `reserved` varchar(64) DEFAULT NULL,",
                "  `org_code` varchar(64) DEFAULT NULL,",
                "  `org_name` varchar(255) DEFAULT NULL,",
                "  `region_code` varchar(32) DEFAULT NULL,",
                "  `extra` varchar(64) DEFAULT NULL,",
                "  `create_time` datetime DEFAULT NULL,",
                "  `update_time` datetime DEFAULT NULL,",
                "  `is_connect` int DEFAULT NULL,",
                "  `is_del` int DEFAULT NULL,",
                "  `sid` varchar(64) DEFAULT NULL,",
                "  `flag` varchar(64) DEFAULT NULL,",
                "  `active` int DEFAULT NULL,",
                "  PRIMARY KEY (`db_id`)",
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;",
                "INSERT INTO `meta_database` VALUES ("
                "'abc123def45678901234567890123456',"
                "'node-1','测试节点','演示库','mysql','10.0.0.1',3306,'demo_db',"
                "'com.mysql.cj.jdbc.Driver','root','ENCRYPTED==',"
                "'jdbc:mysql://10.0.0.1:3306/demo_db',NULL,'张三','13800000000',NULL,"
                "'11370000MB284651XL','省大数据局','370000000000',NULL,"
                "'2025-01-01 00:00:00','2025-01-01 00:00:00',1,0,'sid',NULL,1);",
            ]
        ),
        encoding="utf-8",
    )
    return dump


def test_datasource_mapper_imports_meta_database_redacted(tmp_path: Path) -> None:
    ensure_runtime_schema()
    DatabaseStore()
    dump = _write_meta_database_dump(tmp_path)
    stats = DatasourceEndpointMapper(tenant_id="sd-default").import_dump(dump)
    assert stats.counts.get("meta_database.imported", 0) == 1
    repo = DatasourceEndpointRepository()
    row = repo.get_endpoint("abc123def45678901234567890123456", tenant_id="sd-default")
    assert row is not None
    assert row.display_name == "演示库"
    assert row.db_name == "demo_db"
    assert row.secret_ref is not None
    assert "ENCRYPTED" not in (row.secret_ref or "")
    assert row.summary_json.get("import_kind") == "legacy_meta_database"
    assert "10.0.0.1" in str((row.summary_json or {}).get("host_display") or row.host_ref or "")


def test_datasource_table_list_filters_by_metadata_database_id() -> None:
    meta_repo = MetadataEvidenceRepository()
    table_id = "table-meta-001"
    db_id = "db-meta-001"
    meta_repo.upsert_schema_snapshot(
        {
            "snapshot_ref": f"{table_id}:db_meta_table:{table_id}",
            "resource_code": table_id,
            "binding_code": table_id,
            "schema_json": {
                "meta_id": table_id,
                "database_meta_id": db_id,
                "table_name": "student_info",
                "comment": "学生信息",
            },
        },
        tenant_id="sd-default",
    )
    meta_repo.upsert_schema_snapshot(
        {
            "snapshot_ref": "other:db_meta_table:other",
            "resource_code": "other",
            "binding_code": "other",
            "schema_json": {"meta_id": "other", "database_meta_id": "other-db", "table_name": "noise"},
        },
        tenant_id="sd-default",
    )
    from zw_brain.command.handlers.j2 import datasource_endpoint as handler_mod

    class _Brain:
        pass

    class _Repos:
        datasource_endpoint = DatasourceEndpointRepository()

    class _Deps:
        brain_legacy = _Brain()
        repos = _Repos()

    class _Ctx:
        role = "ROLE_ORGAN_OPERATER"
        skill_id = "datasource.table.list"

    out = handler_mod.handler_datasource_table_list(
        _Deps(),
        _Ctx(),
        {"metadata_database_id": db_id, "tenant_id": "sd-default"},
    )
    assert out["total"] == 1
    assert out["items"][0]["table_name"] == "student_info"
