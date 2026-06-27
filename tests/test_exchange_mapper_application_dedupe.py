from __future__ import annotations

from pathlib import Path

from zw_brain.adapters.legacy.mappers.exchange import ExchangeMapper
from zw_brain.domain.repositories.application import ApplicationRepository
from zw_brain.domain.repositories.approval import ApprovalRepository
from zw_brain.domain.repositories.delivery import DeliveryRepository
from zw_brain.shared.migrate import ensure_runtime_schema

TENANT = "sd-default"


def test_exchange_mapper_collapses_duplicate_legacy_applications() -> None:
    ensure_runtime_schema()
    mapper = ExchangeMapper(tenant_id=TENANT)
    base = {
        "resource_id": "RES-LEGACY-DUP",
        "contact": "平台管理员",
        "apply_org_id": "11370000MB284651XL",
        "apply_org_name": "省大数据局",
        "resource_name": "停车场信息",
        "org_id": "11370000MB284651XL",
        "org_name": "省大数据局",
        "use_reason": "办理业务",
    }

    mapper._map_data_apply(base | {"id": "LEGACY-DUP-1", "status": 9, "create_time": "2024-05-01 10:00:00"}, "dsp-catalog3")
    mapper._map_data_apply(base | {"id": "LEGACY-DUP-2", "status": 7, "create_time": "2024-05-02 10:00:00"}, "dsp-catalog3")

    rows = [
        r
        for r in ApplicationRepository().list_records(tenant_id=TENANT)
        if (r.payload_json or {}).get("resourceId") == "RES-LEGACY-DUP"
    ]

    assert [r.application_code for r in rows] == ["LEGACY-DUP-1"]


def _write_duplicate_apply_dump(tmp_path: Path) -> Path:
    dump = tmp_path / "dump-dsp_catalog-202606261951.sql"
    dump.write_text(
        "\n".join(
            [
                "CREATE TABLE `data_apply` (",
                "  `id` varchar(64) NOT NULL,",
                "  `status` int DEFAULT NULL,",
                "  `resource_id` varchar(64) DEFAULT NULL,",
                "  `contact` varchar(64) DEFAULT NULL,",
                "  `apply_org_id` varchar(64) DEFAULT NULL,",
                "  `apply_org_name` varchar(128) DEFAULT NULL,",
                "  `resource_name` varchar(128) DEFAULT NULL,",
                "  `org_id` varchar(64) DEFAULT NULL,",
                "  `org_name` varchar(128) DEFAULT NULL,",
                "  `use_reason` varchar(255) DEFAULT NULL,",
                "  `create_time` datetime DEFAULT NULL,",
                "  PRIMARY KEY (`id`)",
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;",
                "INSERT INTO `data_apply` VALUES "
                "('LEGACY-DUMP-REJECTED',7,'RES-LEGACY-DUMP-DUP','平台管理员','11370000MB284651XL','省大数据局','停车场信息','11370000MB284651XL','省大数据局','办理业务','2024-05-02 10:00:00'),"
                "('LEGACY-DUMP-APPROVED',9,'RES-LEGACY-DUMP-DUP','平台管理员','11370000MB284651XL','省大数据局','停车场信息','11370000MB284651XL','省大数据局','办理业务','2024-05-01 10:00:00');",
                "CREATE TABLE `data_apply_course` (",
                "  `id` varchar(64) NOT NULL,",
                "  `apply_id` varchar(64) DEFAULT NULL,",
                "  `status` int DEFAULT NULL,",
                "  `check_status` int DEFAULT NULL,",
                "  `node_name` varchar(64) DEFAULT NULL,",
                "  `opinion` varchar(255) DEFAULT NULL,",
                "  `user_code` varchar(64) DEFAULT NULL,",
                "  `user_name` varchar(64) DEFAULT NULL,",
                "  `org_id` varchar(64) DEFAULT NULL,",
                "  `org_name` varchar(128) DEFAULT NULL,",
                "  `create_time` datetime DEFAULT NULL,",
                "  PRIMARY KEY (`id`)",
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;",
                "INSERT INTO `data_apply_course` VALUES "
                "('COURSE-FROM-DUP','LEGACY-DUMP-REJECTED',1,1,'平台审批','同意','U-1','审批员','ORG-P','平台','2024-05-03 10:00:00');",
                "CREATE TABLE `data_apply_authrization` (",
                "  `id` varchar(64) NOT NULL,",
                "  `apply_id` varchar(64) DEFAULT NULL,",
                "  `apply_status` int DEFAULT NULL,",
                "  `status` int DEFAULT NULL,",
                "  `limit_day` int DEFAULT NULL,",
                "  `org_id` varchar(64) DEFAULT NULL,",
                "  `org_name` varchar(128) DEFAULT NULL,",
                "  `handler_code` varchar(64) DEFAULT NULL,",
                "  `handler_name` varchar(64) DEFAULT NULL,",
                "  `res_type` varchar(64) DEFAULT NULL,",
                "  `create_time` datetime DEFAULT NULL,",
                "  PRIMARY KEY (`id`)",
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;",
                "INSERT INTO `data_apply_authrization` VALUES "
                "('AUTHZ-FROM-DUP','LEGACY-DUMP-REJECTED',9,1,180,'11370000MB284651XL','省大数据局','U-2','交付员','table','2024-05-04 10:00:00');",
            ]
        ),
        encoding="utf-8",
    )
    return dump


def test_exchange_import_dump_collapses_duplicate_legacy_applications(tmp_path: Path) -> None:
    ensure_runtime_schema()
    dump = _write_duplicate_apply_dump(tmp_path)

    stats = ExchangeMapper(tenant_id=TENANT).import_dump(dump)

    assert stats.source_counts["data_apply"] == 2
    assert stats.counts["data_apply.imported"] == 1
    assert stats.skipped["data_apply.duplicate_application_collapsed"] == 1
    assert [
        issue["detail"]["canonical_apply_id"]
        for issue in stats.issues
        if issue["type"] == "duplicate_application_collapsed"
    ] == ["LEGACY-DUMP-APPROVED"]

    rows = [
        r
        for r in ApplicationRepository().list_records(tenant_id=TENANT)
        if (r.payload_json or {}).get("resourceId") == "RES-LEGACY-DUMP-DUP"
    ]
    assert [r.application_code for r in rows] == ["LEGACY-DUMP-APPROVED"]
    assert rows[0].status == "approved"

    assert ApprovalRepository().get_case("LEGACY-DUMP-APPROVED", tenant_id=TENANT) is not None
    assert ApprovalRepository().get_case("LEGACY-DUMP-REJECTED", tenant_id=TENANT) is None

    assert DeliveryRepository().get_task("LEGACY-DUMP-REJECTED", tenant_id=TENANT) is None
    task = DeliveryRepository().get_task("LEGACY-DUMP-APPROVED", tenant_id=TENANT)
    assert task is not None
    assert task.application_code == "LEGACY-DUMP-APPROVED"
    assert task.state == "granted"
