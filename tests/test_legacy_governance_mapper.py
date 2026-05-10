"""Regression tests for GovernanceMapper (step 1 of legacy bridging chain)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

BSP_GOVERNANCE_DUMP = """\
DROP TABLE IF EXISTS `sys_department`;
CREATE TABLE `sys_department` (
  `ID` varchar(36) NOT NULL,
  `CODE` varchar(64) DEFAULT NULL,
  `NAME` varchar(255) DEFAULT NULL,
  `PARENT_ID` varchar(36) DEFAULT NULL,
  `REGION_CODE` varchar(32) DEFAULT NULL,
  `STATUS` char(1) DEFAULT '1',
  PRIMARY KEY (`ID`)
) ENGINE=InnoDB;

INSERT INTO `sys_department` VALUES \
('dept-1','370000000000','山东省',NULL,'370000','1'),\
('dept-2','11370000MB284651XL','省大数据局','dept-1','370000','1');

DROP TABLE IF EXISTS `sys_region`;
CREATE TABLE `sys_region` (
  `ID` varchar(36) NOT NULL,
  `CODE` varchar(32) NOT NULL,
  `NAME` varchar(64) NOT NULL,
  `PARENT_CODE` varchar(32) DEFAULT NULL,
  `LEVEL` char(1) DEFAULT NULL,
  `STATUS` char(1) DEFAULT '1',
  PRIMARY KEY (`ID`)
) ENGINE=InnoDB;

INSERT INTO `sys_region` VALUES \
('region-1','370000','山东省','100000','1','1'),\
('region-2','370100','济南市','370000','2','1');

DROP TABLE IF EXISTS `sys_user`;
CREATE TABLE `sys_user` (
  `ID` varchar(36) NOT NULL,
  `ACCOUNT` varchar(128) DEFAULT NULL,
  `NAME` varchar(255) DEFAULT NULL,
  `PASSWORD` varchar(5000) DEFAULT NULL,
  `TOKEN` varchar(5000) DEFAULT NULL,
  `REFRESH_TOKEN` varchar(5000) DEFAULT NULL,
  `VERIFICATION_CODE` varchar(255) DEFAULT NULL,
  `SMS_STATUS` varchar(64) DEFAULT NULL,
  `SESSION` varchar(5000) DEFAULT NULL,
  `COOKIE` varchar(5000) DEFAULT NULL,
  `CLIENT_SECRET` varchar(5000) DEFAULT NULL,
  `MOBILE` varchar(255) DEFAULT NULL,
  `EMAIL` varchar(255) DEFAULT NULL,
  `STATUS` char(1) DEFAULT '1',
  PRIMARY KEY (`ID`)
) ENGINE=InnoDB;

INSERT INTO `sys_user` VALUES \
('u-bound','bound_user','绑定用户','PWD','ACCESS','REFRESH','VCODE','SENT','SESSION','COOKIE','CLIENT_SECRET','13800001111','bound@sd.gov.cn','1'),\
('u-missing','missing_iam','缺 IAM 用户','PWD2','ACCESS2','REFRESH2','VCODE2','SENT','SESSION2','COOKIE2','CLIENT_SECRET2','13800002222','missing@sd.gov.cn','1'),\
('u-no-org','no_org','缺组织用户','PWD3','ACCESS3','REFRESH3','VCODE3','SENT','SESSION3','COOKIE3','CLIENT_SECRET3','13800003333','noorg@sd.gov.cn','1');

DROP TABLE IF EXISTS `sys_role`;
CREATE TABLE `sys_role` (
  `ID` varchar(36) NOT NULL,
  `ROLE_CODE` varchar(64) DEFAULT NULL,
  `ROLE_NAME` varchar(255) DEFAULT NULL,
  `STATUS` char(1) DEFAULT '1',
  PRIMARY KEY (`ID`)
) ENGINE=InnoDB;

INSERT INTO `sys_role` VALUES \
('role-1','ACCOUNT_ADMIN','账号管理员','1'),\
('role-2','DATA_READER','数据读者','1');

DROP TABLE IF EXISTS `sys_user_role`;
CREATE TABLE `sys_user_role` (
  `USER_ID` varchar(36) NOT NULL,
  `ROLE_ID` varchar(36) NOT NULL
) ENGINE=InnoDB;

INSERT INTO `sys_user_role` VALUES \
('u-bound','role-1'),\
('u-bound','role-2'),\
('u-missing','role-1'),\
('u-no-org','role-2');

DROP TABLE IF EXISTS `sys_user_department`;
CREATE TABLE `sys_user_department` (
  `USER_ID` varchar(36) NOT NULL,
  `DEPT_ID` varchar(36) NOT NULL
) ENGINE=InnoDB;

INSERT INTO `sys_user_department` VALUES \
('u-bound','dept-2'),\
('u-missing','dept-2'),\
('u-no-org','missing-dept');

DROP TABLE IF EXISTS `sys_permission`;
CREATE TABLE `sys_permission` (
  `ID` varchar(36) NOT NULL,
  `PERMISSION_CODE` varchar(128) DEFAULT NULL,
  `NAME` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`ID`)
) ENGINE=InnoDB;

INSERT INTO `sys_permission` VALUES \
('perm-1','catalog.entry.query.execute','目录查询'),\
('perm-2','legacy.unmapped.permission','旧未映射权限');

DROP TABLE IF EXISTS `sys_role_permission`;
CREATE TABLE `sys_role_permission` (
  `ROLE_ID` varchar(36) NOT NULL,
  `PERMISSION_ID` varchar(36) NOT NULL
) ENGINE=InnoDB;

INSERT INTO `sys_role_permission` VALUES \
('role-1','perm-1'),\
('role-2','perm-2');

DROP TABLE IF EXISTS `iaf_binding_manifest`;
CREATE TABLE `iaf_binding_manifest` (
  `LEGACY_USER_ID` varchar(36) NOT NULL,
  `IAF_SUB` varchar(128) NOT NULL,
  `PREFERRED_USERNAME` varchar(128) DEFAULT NULL,
  `CLIENT_SECRET` varchar(5000) DEFAULT NULL
) ENGINE=InnoDB;

INSERT INTO `iaf_binding_manifest` VALUES \
('u-bound','iaf-sub-bound','bound_user','MANIFEST_SECRET'),\
('u-no-org','iaf-sub-no-org','no_org','MANIFEST_SECRET2');

DROP TABLE IF EXISTS `capability_mapping_manifest`;
CREATE TABLE `capability_mapping_manifest` (
  `LEGACY_PERMISSION_REF` varchar(128) NOT NULL,
  `CAPABILITY_ID` varchar(128) DEFAULT NULL,
  `SURFACE` varchar(32) DEFAULT NULL,
  `MANIFEST_VERSION` varchar(32) DEFAULT NULL,
  `CLIENT_SECRET` varchar(5000) DEFAULT NULL
) ENGINE=InnoDB;

INSERT INTO `capability_mapping_manifest` VALUES \
('catalog.entry.query.execute','catalog.entry.query','rest','v1','CAPABILITY_SECRET');
"""

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


def test_bsp_governance_import_supports_dry_run_apply_idempotency_and_fail_closed() -> None:
    with TemporaryDirectory() as tmp:
        dumps_dir = Path(tmp) / "dumps"
        dumps_dir.mkdir()
        (dumps_dir / "dump-dsp_bsp-202604000001.sql").write_text(BSP_GOVERNANCE_DUMP, encoding="utf-8")

        db_path = Path(tmp) / "smoke.db"
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)
        os.environ["ZW_BRAIN_LEGACY_DUMPS_DIR"] = str(dumps_dir)
        os.environ["ZW_BRAIN_LEGACY_CACHE_DIR"] = str(Path(tmp) / "cache")

        from zw_brain.adapters.legacy.migration_batch import MigrationOptions, run_migration
        from zw_brain.adapters.legacy.runner import LegacyImportRunner
        from zw_brain.domain.repositories.external_adapter import ExternalAdapterRepository
        from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
        from zw_brain.domain.repositories.legacy_mapping import LegacyObjectMappingRepository
        from zw_brain.shared.migrate import ensure_runtime_schema

        dry_report = run_migration(
            MigrationOptions(
                dumps_dir=dumps_dir,
                db_path=db_path,
                profile="customer-core-v1",
                dry_run=True,
            )
        )
        dry_stats = dry_report["imports"][0]["mappers"][0]
        assert dry_report["dry_run"] is True
        assert dry_stats["source_counts"] == {
            "capability_mapping_manifest": 1,
            "iaf_binding_manifest": 2,
            "sys_department": 2,
            "sys_permission": 2,
            "sys_region": 2,
            "sys_role": 2,
            "sys_role_permission": 2,
            "sys_user": 3,
            "sys_user_department": 3,
            "sys_user_role": 4,
        }
        assert dry_stats["target_counts"]["actor_projection"] == 3
        assert dry_stats["target_counts"]["actor_org_role_binding"] == 2
        assert {issue["type"] for issue in dry_stats["issues"]} == {"iam_account_missing", "missing_org_relationship", "unmapped_permission"}
        assert not db_path.exists()
        assert "CLIENT_SECRET" not in json.dumps(dry_report, ensure_ascii=False).upper()
        assert "ACCESS" not in json.dumps(dry_report, ensure_ascii=False)
        assert "REFRESH" not in json.dumps(dry_report, ensure_ascii=False)

        ensure_runtime_schema()
        stats = LegacyImportRunner().import_schema("dsp_bsp")
        assert stats.to_dict()["mode"] == "apply"
        gov = GovernanceProjectionRepository()
        actors = {item.external_actor_id: item for item in gov.list_actors(tenant_id="sd-default")}
        assert actors["iaf-sub-bound"].status == "active"
        assert actors["iaf-sub-bound"].role_codes_json == ["ACCOUNT_ADMIN", "DATA_READER"]
        assert actors["u-missing"].status == "iam_account_missing"
        assert actors["u-missing"].role_codes_json == []
        assert actors["iaf-sub-no-org"].status == "unmatched"
        assert actors["iaf-sub-no-org"].role_codes_json == []
        assert {item.role_code for item in gov.list_actor_org_role_bindings(tenant_id="sd-default", external_actor_id="iaf-sub-bound")} == {"ACCOUNT_ADMIN", "DATA_READER"}
        assert gov.list_actor_org_role_bindings(tenant_id="sd-default", external_actor_id="u-missing") == []
        candidates = gov.list_policy_candidates(tenant_id="sd-default")
        assert [(item.legacy_permission_ref, item.legacy_role_ref, item.capability_id) for item in candidates] == [("catalog.entry.query.execute", "ACCOUNT_ADMIN", "catalog.entry.query")]

        actor_profile_json = json.dumps([item.profile_json for item in actors.values()], ensure_ascii=False).lower()
        for forbidden in ["password", "token", "refresh_token", "verification_code", "sms_status", "session", "cookie", "client_secret"]:
            assert forbidden not in actor_profile_json
        assert "13800001111" in actor_profile_json

        LegacyImportRunner().import_schema("dsp_bsp")
        assert len(gov.list_actors(tenant_id="sd-default")) == 3
        assert len(gov.list_actor_org_role_bindings(tenant_id="sd-default", external_actor_id="iaf-sub-bound")) == 2
        assert len(gov.list_policy_candidates(tenant_id="sd-default")) == 1
        assert len(LegacyObjectMappingRepository().list_mappings(tenant_id="sd-default", canonical_type="capability")) == 1
        runs = ExternalAdapterRepository().list_run_records(tenant_id="sd-default", adapter_slug="legacy.bsp.governance")
        assert len(runs) == 1
        assert runs[0].status == "partial_failure"
        receipt_text = json.dumps(runs[0].receipt_json, ensure_ascii=False).lower()
        for forbidden in ["password", "token", "refresh_token", "verification_code", "sms_status", "session", "cookie", "client_secret"]:
            assert forbidden not in receipt_text
