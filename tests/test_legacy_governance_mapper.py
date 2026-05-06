"""Regression tests for GovernanceMapper (step 1 of legacy bridging chain)."""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory


GOVERNANCE_DUMP = """\
DROP TABLE IF EXISTS `pub_organ`;
CREATE TABLE `pub_organ` (
  `ID` varchar(36) NOT NULL,
  `CODE` varchar(32) NOT NULL,
  `NAME` varchar(512) NOT NULL,
  `SHORT_NAME` varchar(255) NOT NULL,
  `REGION_CODE` varchar(12) NOT NULL,
  `REGION_NAME` varchar(255) NOT NULL,
  `STATUS` char(1) DEFAULT '1',
  `ORGAN_TYPE` varchar(36) DEFAULT '1',
  `ORGAN_LEVEL` char(1) DEFAULT NULL,
  `SOCIETY_CODE` varchar(50) DEFAULT NULL,
  `ORG_NUM` varchar(50) DEFAULT NULL,
  `TRACE_CODE` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`ID`)
) ENGINE=InnoDB;

INSERT INTO `pub_organ` VALUES \
('id-1','370000000000','山东省','山东','370000','山东省','1','1','1','370000000000','SD','370000000000'),\
('id-2','11370000MB284651XL','省大数据局','大数据局','370000','山东省','1','2','2','11370000MB284651XL','BDB','370000000000-11370000MB284651XL');

DROP TABLE IF EXISTS `pub_region`;
CREATE TABLE `pub_region` (
  `CODE` varchar(32) NOT NULL,
  `NAME` varchar(64) NOT NULL,
  `SHORT_CODE` varchar(32) DEFAULT NULL,
  `GRADE` char(1) NOT NULL,
  `PARENT_CODE` varchar(12) NOT NULL,
  `STATUS` char(1) DEFAULT '1',
  `TREE_CODE` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`CODE`)
) ENGINE=InnoDB;

INSERT INTO `pub_region` VALUES \
('370000','山东省','SD','1','100000','1','370000'),\
('370100','济南市','JN','2','370000','1','370000-370100');

DROP TABLE IF EXISTS `pub_user`;
CREATE TABLE `pub_user` (
  `ID` varchar(36) NOT NULL,
  `ACCOUNT` varchar(128) NOT NULL,
  `NAME` varchar(255) NOT NULL,
  `PASSWORD` varchar(5000) DEFAULT NULL,
  `MOBILE` varchar(255) DEFAULT NULL,
  `EMAIL` varchar(255) DEFAULT NULL,
  `ROLE_VALUE` varchar(1024) DEFAULT NULL,
  `ORG_CODE` varchar(36) DEFAULT NULL,
  `STATUS` char(1) DEFAULT '1',
  `OTP_KEY` varchar(255) DEFAULT NULL,
  `SENSITIVE_HMAC` varchar(5000) DEFAULT NULL,
  `UKEY` varchar(255) DEFAULT NULL,
  `IP_LIST` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`ID`)
) ENGINE=InnoDB;

INSERT INTO `pub_user` VALUES \
('uid-1','zhangsan','张三','REAL_HASHED_PWD','13800001111','zhangsan@sd.gov.cn','r-admin,r-reader','11370000MB284651XL','1','REAL_OTP','REAL_HMAC','REAL_UKEY','10.0.0.1');

DROP TABLE IF EXISTS `pub_role`;
CREATE TABLE `pub_role` (
  `ID` varchar(36) NOT NULL,
  `NAME` varchar(255) NOT NULL,
  `VALUE` varchar(255) NOT NULL,
  `TYPE` char(1) NOT NULL,
  `SORT_ORDER` int(11) NOT NULL,
  `STATUS` char(1) DEFAULT '1',
  `HMAC` varchar(5000) DEFAULT NULL,
  PRIMARY KEY (`ID`)
) ENGINE=InnoDB;

INSERT INTO `pub_role` VALUES \
('role-uuid-1','管理员','r-admin','1',1,'1','REAL_ROLE_HMAC'),\
('role-uuid-2','只读用户','r-reader','1',2,'1','REAL_ROLE_HMAC2');
"""


def test_governance_mapper_imports_four_projection_kinds_and_drops_secrets() -> None:
    with TemporaryDirectory() as tmp:
        dumps_dir = Path(tmp) / "dumps"
        dumps_dir.mkdir()
        (dumps_dir / "dump-dsp_bsp-202604000000.sql").write_text(GOVERNANCE_DUMP, encoding="utf-8")

        os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "smoke.db")
        os.environ["ZW_BRAIN_LEGACY_DUMPS_DIR"] = str(dumps_dir)
        os.environ["ZW_BRAIN_LEGACY_CACHE_DIR"] = str(Path(tmp) / "cache")

        from zw_brain.adapters.legacy import LegacyImportRunner
        from zw_brain.domain.repositories.external_adapter import ExternalAdapterRepository
        from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
        from zw_brain.domain.repositories.legacy_mapping import LegacyObjectMappingRepository
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        runner = LegacyImportRunner()
        stats = runner.import_schema("dsp_bsp")
        assert stats is not None
        counts = stats.to_dict()["counts"]
        assert counts == {
            "pub_organ.imported": 2,
            "pub_region.imported": 2,
            "pub_user.imported": 1,
            "pub_role.imported": 2,
        }

        gov = GovernanceProjectionRepository()
        orgs = {o.org_code: o for o in gov.list_orgs(tenant_id="sd-default")}
        assert orgs["11370000MB284651XL"].org_name == "省大数据局"
        # parent derived from TRACE_CODE
        assert orgs["11370000MB284651XL"].parent_org_code == "370000000000"

        regions = {r.region_code: r for r in gov.list_regions(tenant_id="sd-default")}
        assert regions["370100"].parent_region_code == "370000"
        assert regions["370100"].region_level == "2"

        actors = {a.external_actor_id: a for a in gov.list_actors(tenant_id="sd-default")}
        actor = actors["uid-1"]
        # business-visible sensitive flow through (mask layer is read-side)
        assert actor.profile_json["mobile"] == "13800001111"
        assert actor.profile_json["email"] == "zhangsan@sd.gov.cn"
        # real secrets: dropped at mapper boundary
        assert "password" not in {k.lower() for k in actor.profile_json}
        assert "otp_key" not in {k.lower() for k in actor.profile_json}
        assert "sensitive_hmac" not in {k.lower() for k in actor.profile_json}
        assert "ukey" not in {k.lower() for k in actor.profile_json}
        assert "ip_list" not in {k.lower() for k in actor.profile_json}
        # role codes parsed from comma-joined ROLE_VALUE
        assert actor.role_codes_json == ["r-admin", "r-reader"]

        roles = {r.role_code: r for r in gov.list_roles(tenant_id="sd-default")}
        assert set(roles.keys()) == {"r-admin", "r-reader"}
        # HMAC dropped
        assert all("hmac" not in {k.lower() for k in r.profile_json} for r in roles.values())

        legacy = LegacyObjectMappingRepository()
        org_mappings = legacy.list_mappings(tenant_id="sd-default", canonical_type="OrgProjectionRecord")
        assert {m.legacy_object_ref for m in org_mappings} == {"370000000000", "11370000MB284651XL"}
        actor_mappings = legacy.list_mappings(tenant_id="sd-default", canonical_type="ActorProjectionRecord")
        assert {m.legacy_object_ref for m in actor_mappings} == {"uid-1"}

        runs = ExternalAdapterRepository().list_run_records(tenant_id="sd-default", adapter_slug="legacy.bsp.governance")
        assert len(runs) == 1
        assert runs[0].status == "succeeded"
        assert runs[0].target_count == 7  # 2 organs + 2 regions + 1 user + 2 roles

        # Re-running is idempotent: same single AdapterRunRecord, projection counts unchanged.
        runner.import_schema("dsp_bsp")
        runs_after = ExternalAdapterRepository().list_run_records(tenant_id="sd-default", adapter_slug="legacy.bsp.governance")
        assert len(runs_after) == 1
        assert len(gov.list_orgs(tenant_id="sd-default")) == 2
