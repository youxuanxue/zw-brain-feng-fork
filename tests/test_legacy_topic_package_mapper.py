"""Regression test for TopicPackageMapper (A1 customer-grade demo seed)."""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

EXAMPLE_DUMP = """\
DROP TABLE IF EXISTS `data_example`;
CREATE TABLE `data_example` (
  `id` varchar(36) NOT NULL,
  `example_name` varchar(255) NOT NULL,
  `org_code` varchar(64) NOT NULL,
  `org_name` varchar(128) NOT NULL,
  `region_code` varchar(36) NOT NULL,
  `region_name` varchar(255) NOT NULL,
  `field_type` varchar(255) NOT NULL,
  `example_desc` text NOT NULL,
  `process_desc` text,
  `result_desc` text,
  `visit_count` int(11) DEFAULT '0',
  `status` tinyint(2) DEFAULT NULL,
  `example_creator` varchar(32) NOT NULL,
  `create_time` datetime NOT NULL,
  `opinion` varchar(255) DEFAULT NULL,
  `push_status` char(1) DEFAULT '0',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB;

-- Cover every legacy status code so the canonical state-machine walk stays honest:
--   0 草稿 → configuring     1/2 待审核/待发布 → submitted     3/5 驳回 → rejected     4 已发布 → published
INSERT INTO `data_example` VALUES \
('eg-pub','婚姻登记全省通办','11370000MB284651XL','省大数据局','370000','山东省','11','让数据为爱多跑腿','数据共享','基层减负',13,4,'admin','2025-04-11 11:21:07','通过','1'),\
('eg-draft','出生一件事','11370000MB284651XL','省大数据局','370000','山东省','11,16','出生户籍医保等一站办理',NULL,NULL,21,0,'admin','2025-04-11 11:21:07','',NULL),\
('eg-pending','公司变更登记','11370000MB284651XL','省大数据局','370000','山东省','01','企业变更登记案例',NULL,NULL,5,1,'admin','2025-04-11 11:21:07','',NULL),\
('eg-rejected','不动产交易登记一体化平台','11370000MB284651XL','省大数据局','370000','山东省','04','不动产登记一体化',NULL,NULL,3,5,'admin','2025-04-11 11:21:07','发布驳回',NULL);

DROP TABLE IF EXISTS `data_example_item`;
CREATE TABLE `data_example_item` (
  `example_item_id` varchar(36) NOT NULL,
  `example_id` varchar(36) NOT NULL,
  `task_code` varchar(255) DEFAULT NULL,
  `task_name` varchar(255) DEFAULT NULL,
  `material_id` varchar(255) DEFAULT NULL,
  `material_name` varchar(255) DEFAULT NULL,
  `res_id` varchar(255) DEFAULT NULL,
  `res_name` varchar(255) DEFAULT NULL,
  `cata_id` varchar(255) DEFAULT NULL,
  `cata_title` varchar(255) DEFAULT NULL,
  `res_type` varchar(255) DEFAULT NULL,
  `res_status` varchar(50) DEFAULT '0',
  PRIMARY KEY (`example_item_id`)
) ENGINE=InnoDB;

INSERT INTO `data_example_item` VALUES \
('it-1','eg-pub','婚姻登记全省通办',NULL,NULL,NULL,'res-pop-001','人口基本信息_库表信息','cata-pop','人口基本信息','table','0'),\
('it-2','eg-draft','出生一件事',NULL,NULL,NULL,'res-pop-002','学前教育幼儿基本信息','cata-pop','人口基本信息','table','0'),\
('it-3','eg-pending','公司变更登记',NULL,NULL,NULL,'res-corp-001','企业基本信息','cata-corp','企业基本信息','table','0'),\
('it-4','eg-rejected','不动产登记',NULL,NULL,NULL,'res-realestate-001','房地产开发项目信息','cata-real','房地产','table','0');

DROP TABLE IF EXISTS `data_example_contact`;
CREATE TABLE `data_example_contact` (
  `id` varchar(255) NOT NULL,
  `contact` varchar(255) DEFAULT NULL,
  `contact_phone` varchar(255) NOT NULL,
  `region_code` varchar(255) DEFAULT NULL,
  `region_name` varchar(255) DEFAULT NULL,
  `org_code` varchar(255) DEFAULT NULL,
  `org_name` varchar(255) DEFAULT NULL,
  `title` varchar(255) DEFAULT NULL,
  `status` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB;

INSERT INTO `data_example_contact` VALUES \
('c-1','韩岩','15585294353','370000','山东省','11370000MB284651XL','省大数据局','负责人','1');

DROP TABLE IF EXISTS `data_example_file`;
CREATE TABLE `data_example_file` (
  `example_file_id` varchar(255) NOT NULL,
  `example_id` varchar(255) NOT NULL,
  `file_type` varchar(255) NOT NULL,
  `file_path` text NOT NULL,
  PRIMARY KEY (`example_file_id`)
) ENGINE=InnoDB;

INSERT INTO `data_example_file` VALUES \
('f-1','eg-pub','1','{\\"file_path\\":\\"/files/abc.pdf\\",\\"file_name\\":\\"婚姻登记流程.pdf\\",\\"file_format\\":\\"pdf\\",\\"file_size\\":\\"320KB\\"}');

DROP TABLE IF EXISTS `data_example_feedback`;
CREATE TABLE `data_example_feedback` (
  `id` varchar(255) NOT NULL,
  `example_id` varchar(255) NOT NULL,
  `res_id` varchar(255) NOT NULL,
  `res_name` varchar(255) NOT NULL,
  `example_name` varchar(255) NOT NULL,
  `is_apply` varchar(255) DEFAULT NULL,
  `is_need` varchar(255) DEFAULT NULL,
  `org_code` varchar(255) DEFAULT NULL,
  `org_name` varchar(255) DEFAULT NULL,
  `creator` varchar(255) DEFAULT NULL,
  `create_time` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB;

INSERT INTO `data_example_feedback` VALUES \
('fb-1','eg-pub','res-pop-001','人口基本信息','婚姻登记全省通办','0','0','11370000MB284651XL','省大数据局','admin','2023-11-22 14:30:11');
"""


def test_topic_package_mapper_honors_legacy_status_with_evidence_and_idempotent_replay() -> None:
    with TemporaryDirectory() as tmp:
        dumps_dir = Path(tmp) / "dumps"
        dumps_dir.mkdir()
        (dumps_dir / "dump-dsp_example-202604000000.sql").write_text(EXAMPLE_DUMP, encoding="utf-8")

        os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "smoke.db")
        os.environ["ZW_BRAIN_LEGACY_DUMPS_DIR"] = str(dumps_dir)
        os.environ["ZW_BRAIN_LEGACY_CACHE_DIR"] = str(Path(tmp) / "cache")

        from zw_brain.adapters.legacy import LegacyImportRunner
        from zw_brain.domain.repositories.external_adapter import ExternalAdapterRepository
        from zw_brain.domain.repositories.legacy_mapping import LegacyObjectMappingRepository
        from zw_brain.domain.repositories.topic_package import TopicPackageRepository
        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.sensitive_mask import apply_field_masks

        ensure_runtime_schema()
        runner = LegacyImportRunner()
        stats = runner.import_schema("dsp_example")
        counts = stats.to_dict()["counts"]
        assert counts["data_example.imported"] == 4
        assert counts["data_example_item.attached"] == 4
        assert counts["data_example_contact.attached"] == 1
        assert counts["data_example_file.attached"] == 1
        assert counts["data_example_feedback.attached"] == 1

        topic = TopicPackageRepository()
        packages = {p.package_code: p for p in topic.list_packages(tenant_id="sd-default")}
        assert set(packages.keys()) == {"eg-pub", "eg-draft", "eg-pending", "eg-rejected"}

        # Honest legacy-status walk — the mapper must NOT lie about the legacy state:
        #   status=4 (已发布)  → published
        #   status=1 (待审核)  → submitted (not published — legacy hadn't approved)
        #   status=0 (草稿)    → configuring (not even submitted)
        #   status=5 (发布驳回) → rejected
        assert packages["eg-pub"].status == "published"
        assert packages["eg-pending"].status == "submitted"
        assert packages["eg-draft"].status == "configuring"
        assert packages["eg-rejected"].status == "rejected"

        # contacts embedded raw, mask layer can sanitize them on read
        contacts_raw = packages["eg-pub"].display_snapshot_json["contacts"]
        assert contacts_raw[0]["contact_name"] == "韩岩"
        assert contacts_raw[0]["contact_phone"] == "15585294353"
        masked = apply_field_masks({"contacts": contacts_raw}, role="external")
        assert masked["contacts"][0]["contact_name"] == "韩*"
        assert masked["contacts"][0]["contact_phone"] == "155****4353"

        # items linked
        items = topic.list_items("eg-pub", tenant_id="sd-default")
        assert len(items) == 1
        assert items[0].title == "人口基本信息_库表信息"
        assert items[0].ref_type == "table"

        # evidence: file (JSON-string `file_path` column parsed to dict) + feedback
        evidence = topic.list_evidence("eg-pub", tenant_id="sd-default")
        kinds = {e.evidence_type for e in evidence}
        assert kinds == {"file", "feedback"}
        file_evidence = next(e for e in evidence if e.evidence_type == "file")
        assert file_evidence.title == "婚姻登记流程.pdf"
        assert file_evidence.content_json["file_format"] == "pdf"

        # legacy mapping
        legacy = LegacyObjectMappingRepository()
        topic_maps = legacy.list_mappings(tenant_id="sd-default", canonical_type="TopicPackageRecord")
        assert {m.legacy_object_ref for m in topic_maps} == {"eg-pub", "eg-draft", "eg-pending", "eg-rejected"}

        runs_before = ExternalAdapterRepository().list_run_records(
            tenant_id="sd-default", adapter_slug="legacy.sharezone.example.import"
        )
        assert len(runs_before) == 1 and runs_before[0].status == "succeeded" and runs_before[0].target_count == 4

        # ── Idempotency: re-running the same dump must not create duplicate packages,
        #    extra evidence rows, or a second AdapterRunRecord. ──
        runner.import_schema("dsp_example")
        packages_after = topic.list_packages(tenant_id="sd-default")
        assert len(packages_after) == 4
        # evidence count for eg-pub stable (would double if attach_evidence wasn't deduped or wiped)
        evidence_after = topic.list_evidence("eg-pub", tenant_id="sd-default")
        assert len(evidence_after) == len(evidence)
        # AdapterRunRecord uses idempotency_key=(adapter_slug, dump_filename) — single record, count updated
        runs_after = ExternalAdapterRepository().list_run_records(
            tenant_id="sd-default", adapter_slug="legacy.sharezone.example.import"
        )
        assert len(runs_after) == 1
        # Status doesn't regress on re-import (eg-pub stays published, not pulled back to draft)
        packages_after_map = {p.package_code: p for p in packages_after}
        assert packages_after_map["eg-pub"].status == "published"
        assert packages_after_map["eg-draft"].status == "configuring"
