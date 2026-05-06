"""Regression tests for ExchangeMapper (step 5 of legacy bridging chain — require side)."""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

REQUIRE_DUMP = """\
DROP TABLE IF EXISTS `data_require`;
CREATE TABLE `data_require` (
  `require_id` varchar(32) NOT NULL,
  `task_id` varchar(32) DEFAULT NULL,
  `require_title` varchar(255) NOT NULL,
  `require_content` varchar(255) DEFAULT NULL,
  `share_type` int(11) NOT NULL,
  `update_cycle` int(11) NOT NULL,
  `requireorg_ids` varchar(2000) NOT NULL,
  `requireorg_names` varchar(2000) NOT NULL,
  `data_source` varchar(10) NOT NULL,
  `dutyorg_id` varchar(32) DEFAULT NULL,
  `dutyorg_name` varchar(255) DEFAULT NULL,
  `dutyregion_code` varchar(32) DEFAULT NULL,
  `status` int(11) NOT NULL,
  `create_time` datetime NOT NULL,
  PRIMARY KEY (`require_id`)
) ENGINE=InnoDB;

INSERT INTO `data_require` VALUES \
('req-1','task-1','人口数据共享需求','需要查询省内常住人口基本信息',1,1,'org-a,org-b','省人社厅|省民政厅','2','11370000004504927A','省公安厅','370000',6,'2025-04-11 11:21:07'),\
('req-2','task-1','停车场数据需求','停车场实时数据查询',2,1,'org-c','省交通厅','1','11370000MB284651XL','省大数据局','370000',1,'2025-04-11 11:21:07');

DROP TABLE IF EXISTS `data_original_require`;
CREATE TABLE `data_original_require` (
  `id` varchar(32) NOT NULL,
  `business_id` varchar(32) DEFAULT NULL,
  `require_title` varchar(255) NOT NULL,
  `require_content` varchar(255) DEFAULT NULL,
  `org_id` varchar(32) NOT NULL,
  `org_name` varchar(255) NOT NULL,
  `region_code` varchar(32) NOT NULL,
  `region_name` varchar(255) NOT NULL,
  `share_type` int(11) NOT NULL,
  `update_cycle` int(11) NOT NULL,
  `status` int(11) NOT NULL,
  `creator` varchar(32) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB;

INSERT INTO `data_original_require` VALUES \
('orig-1','biz-1','基层人口数据需求','基层填报需要常住人口信息','11370000XYZ','基层街道办','370102','市中区',1,2,2,'creator-1'),\
('orig-2','biz-2','法人信息上报需求','法人单位信息','11370000ABC','市监局','370100','济南市',1,1,5,'creator-2');
"""


def test_exchange_mapper_imports_data_require_and_original_require() -> None:
    with TemporaryDirectory() as tmp:
        dumps_dir = Path(tmp) / "dumps"
        dumps_dir.mkdir()
        (dumps_dir / "dump-dsp_require-202604000000.sql").write_text(REQUIRE_DUMP, encoding="utf-8")

        os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "smoke.db")
        os.environ["ZW_BRAIN_LEGACY_DUMPS_DIR"] = str(dumps_dir)
        os.environ["ZW_BRAIN_LEGACY_CACHE_DIR"] = str(Path(tmp) / "cache")

        from zw_brain.adapters.legacy import LegacyImportRunner
        from zw_brain.domain.repositories.application import ApplicationRepository
        from zw_brain.domain.repositories.external_adapter import ExternalAdapterRepository
        from zw_brain.domain.repositories.legacy_mapping import LegacyObjectMappingRepository
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        runner = LegacyImportRunner()
        stats = runner.import_schema("dsp_require")
        assert stats.to_dict()["counts"] == {
            "data_require.imported": 2,
            "data_original_require.imported": 2,
        }

        records = {r.application_code: r for r in ApplicationRepository().list_records()}
        assert {"req-1", "req-2", "orig-1", "orig-2"} <= set(records.keys())

        # Status remap: data_require.status=6 → approved, status=1 → submitted
        assert records["req-1"].status == "approved"
        assert records["req-2"].status == "submitted"
        # data_original_require.status=2 → approved, status=5 → effective
        assert records["orig-1"].status == "approved"
        assert records["orig-2"].status == "effective"

        # kind discriminator preserved in payload_json
        assert records["req-1"].payload_json["kind"] == "require"
        assert records["orig-1"].payload_json["kind"] == "original_require"
        # multi-org applicant: first piece by '|'
        assert records["req-1"].applicant_org == "省人社厅"

        legacy = LegacyObjectMappingRepository()
        require_maps = legacy.list_mappings(tenant_id="sd-default", canonical_type="application_record")
        assert {m.legacy_object_ref for m in require_maps} == {"req-1", "req-2", "orig-1", "orig-2"}

        runs = ExternalAdapterRepository().list_run_records(tenant_id="sd-default", adapter_slug="legacy.exchange.import")
        assert len(runs) == 1 and runs[0].status == "succeeded" and runs[0].target_count == 4
