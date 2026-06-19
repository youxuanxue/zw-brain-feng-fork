"""阶段 F：BSP 权限样本链路集成验收（dry-run → apply → review → tenant 策略）。"""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

from zw_brain.command.brain import BrainService
from zw_brain.domain import policy
from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
from zw_brain.shared import audit as audit_bus
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.migrate import ensure_runtime_schema
from zw_brain.shared.state_store import StateStore

# PUB 批次治理基础数据（pub_organ / pub_region / pub_user / pub_user_organ_role +
# iaf_binding_manifest / role_mapping_manifest）。内联以避免依赖 main 已退役的旧测试文件。
_PUB_BATCH_GOVERNANCE_DUMP = """\
DROP TABLE IF EXISTS `pub_organ`;
CREATE TABLE `pub_organ` (
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
  `ID` varchar(36) NOT NULL,
  PRIMARY KEY (`ID`)
) ENGINE=InnoDB;

INSERT INTO `pub_organ` VALUES \
('ORG-A','机构A','机构A','370000','山东省','1','1','1','SOC-A','1','370000','id-org-a');

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

INSERT INTO `pub_region` VALUES ('370000','山东省','SD','1','100000','1','370000');

DROP TABLE IF EXISTS `pub_user`;
CREATE TABLE `pub_user` (
  `ID` varchar(36) NOT NULL,
  `ACCOUNT` varchar(128) NOT NULL,
  `NAME` varchar(255) NOT NULL,
  `USER_CODE` varchar(36) NOT NULL,
  `ROLE_CODE` varchar(64) DEFAULT NULL,
  `ROLE_VALUE` varchar(1024) DEFAULT NULL,
  `ORG_CODE` varchar(36) DEFAULT NULL,
  `STATUS` char(1) DEFAULT '1',
  PRIMARY KEY (`ID`)
) ENGINE=InnoDB;

INSERT INTO `pub_user` VALUES \
('U001','user_a','用户A','U001','ROLE_ORGAN_MANAGER','ROLE_ORGAN_MANAGER','ORG-A','1'),\
('U002','user_b','用户B','U002','ROLE_ORGAN_OPERATER','ROLE_ORGAN_OPERATER','ORG-A','1'),\
('U003','user_c','用户C','U003','LEGACY_ROLE_X01','LEGACY_ROLE_X01','ORG-A','1');

DROP TABLE IF EXISTS `pub_user_organ_role`;
CREATE TABLE `pub_user_organ_role` (
  `ID` varchar(36) NOT NULL,
  `ORG_CODE` varchar(36) NOT NULL,
  `ROLE_CODE` varchar(64) NOT NULL,
  `USER_CODE` varchar(36) NOT NULL,
  `IS_MAIN_ORG` char(1) DEFAULT '1',
  PRIMARY KEY (`ID`)
) ENGINE=InnoDB;

INSERT INTO `pub_user_organ_role` VALUES \
('UOR1','ORG-A','ROLE_ORGAN_MANAGER','U001','1'),\
('UOR2','ORG-A','ROLE_ORGAN_OPERATER','U002','1'),\
('UOR3','ORG-B','ROLE_ORGAN_OPERATER','U002','1');

DROP TABLE IF EXISTS `pub_user_role`;
CREATE TABLE `pub_user_role` (
  `ROLE_CODE` varchar(36) NOT NULL,
  `USER_CODE` varchar(36) NOT NULL,
  `APP_CODE` varchar(36) NOT NULL,
  `HMAC` varchar(5000) DEFAULT NULL,
  PRIMARY KEY (`ROLE_CODE`,`USER_CODE`,`APP_CODE`)
) ENGINE=InnoDB;

-- D63：U001 在 pub_user_role 另有 ROLE_BUSIAUDIT（按 APP 域记，无 ORG）→ 应 materialize 到主机构。
INSERT INTO `pub_user_role` VALUES \
('ROLE_BUSIAUDIT','U001','DSP-CATALOG',NULL);

DROP TABLE IF EXISTS `iaf_binding_manifest`;
CREATE TABLE `iaf_binding_manifest` (
  `LEGACY_USER_ID` varchar(36) NOT NULL,
  `LEGACY_USER_CODE` varchar(36) DEFAULT NULL,
  `IAF_SUB` varchar(128) NOT NULL
) ENGINE=InnoDB;

INSERT INTO `iaf_binding_manifest` VALUES \
('U001','U001','iaf-sub-a'),\
('U002','U002','iaf-sub-b');

DROP TABLE IF EXISTS `role_mapping_manifest`;
CREATE TABLE `role_mapping_manifest` (
  `LEGACY_ROLE_REF` varchar(128) NOT NULL,
  `TARGET_TYPE` varchar(16) NOT NULL,
  `TARGET_ROLE_CODE` varchar(64) DEFAULT NULL,
  `TARGET_TAG` varchar(64) DEFAULT NULL
) ENGINE=InnoDB;

INSERT INTO `role_mapping_manifest` VALUES \
('ROLE_ORGAN_MANAGER','role','ROLE_ORGAN_MANAGER',NULL),\
('ROLE_ORGAN_OPERATER','role','ROLE_ORGAN_OPERATER',NULL),\
('ROLE_BUSIAUDIT','role','ROLE_BUSIAUDIT',NULL),\
('LEGACY_ROLE_X01','role',NULL,NULL);
"""

# 在 PUB 批次样本基础上追加「可映射 FUNC → audit.list」与 capability manifest。
_PIPELINE_DUMP_SUFFIX = """
DROP TABLE IF EXISTS `pub_role`;
CREATE TABLE `pub_role` (
  `CODE` varchar(64) NOT NULL,
  `NAME` varchar(255) NOT NULL,
  PRIMARY KEY (`CODE`)
) ENGINE=InnoDB;

INSERT INTO `pub_role` VALUES ('ROLE_BUSIAUDIT','业务运营员');

DROP TABLE IF EXISTS `pub_function`;
CREATE TABLE `pub_function` (
  `CODE` varchar(64) NOT NULL,
  `NAME` varchar(255) NOT NULL,
  PRIMARY KEY (`CODE`)
) ENGINE=InnoDB;

INSERT INTO `pub_function` VALUES ('FUNC_AUDIT_LIST','审计列表');

DROP TABLE IF EXISTS `pub_role_function`;
CREATE TABLE `pub_role_function` (
  `ROLE_CODE` varchar(64) NOT NULL,
  `FUNCTION_CODE` varchar(64) NOT NULL
) ENGINE=InnoDB;

INSERT INTO `pub_role_function` VALUES ('ROLE_BUSIAUDIT','FUNC_AUDIT_LIST');

DROP TABLE IF EXISTS `capability_mapping_manifest`;
CREATE TABLE `capability_mapping_manifest` (
  `LEGACY_PERMISSION_REF` varchar(128) NOT NULL,
  `CAPABILITY_ID` varchar(128) NOT NULL,
  `SURFACE` varchar(32) DEFAULT NULL,
  `CANDIDATE_STATUS` varchar(32) DEFAULT NULL,
  `MANIFEST_VERSION` varchar(32) DEFAULT NULL
) ENGINE=InnoDB;

INSERT INTO `capability_mapping_manifest` VALUES \
('FUNC_AUDIT_LIST','audit.list','webui','pending_review','pipeline-e2e-v1');
"""


def _pipeline_dump() -> str:
    return _PUB_BATCH_GOVERNANCE_DUMP + _PIPELINE_DUMP_SUFFIX


def _bootstrap_service(tmp: str) -> tuple[BrainService, GovernanceProjectionRepository]:
    db_path = Path(tmp) / "pipeline.db"
    os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)
    ensure_runtime_schema()
    database_store = DatabaseStore()
    audit_bus.configure_sink(database_store.append_audit_event)
    service = BrainService(state_store=StateStore(database_store=database_store))
    return service, GovernanceProjectionRepository()


def _import_pipeline_dump(tmp: str, *, dry_run: bool) -> dict:
    dumps_dir = Path(tmp) / "dumps"
    dumps_dir.mkdir(parents=True, exist_ok=True)
    dump_path = dumps_dir / "dump-dsp_bsp-20260520-pipeline-e2e.sql"
    dump_path.write_text(_pipeline_dump(), encoding="utf-8")

    from zw_brain.adapters.legacy.mappers.governance import GovernanceMapper

    stats = GovernanceMapper().import_dump(dump_path, dry_run=dry_run)
    return stats.to_dict()


def test_pipeline_dry_run_then_apply_review_and_tenant_policy() -> None:
    policy.assert_no_legacy_role_codes()

    with TemporaryDirectory() as tmp:
        service, gov = _bootstrap_service(tmp)

        dry = _import_pipeline_dump(tmp, dry_run=True)
        assert dry["mode"] == "dry-run"
        assert dry["target_counts"].get("legacy_policy_mapping_candidate", 0) >= 1
        assert dry["target_counts"].get("actor_org_role_binding", 0) >= 2

        applied = _import_pipeline_dump(tmp, dry_run=False)
        assert applied["mode"] == "apply"

        # D63：U001 的产品角色 = organ(ROLE_ORGAN_MANAGER) ∪ pub_user_role(ROLE_BUSIAUDIT)，
        # 证明 pub_user_role 经 pipeline 流程也被 materialize（按主机构落点、与 organ 合并去重）。
        u001_roles = {
            b.role_code
            for b in gov.list_actor_org_role_bindings(tenant_id="sd-default", binding_status="active")
            if b.external_actor_id == "iaf-sub-a"
        }
        assert u001_roles == {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"}, u001_roles

        candidates = gov.list_policy_candidates(tenant_id="sd-default")
        audit_candidates = [item for item in candidates if item.capability_id == "audit.list"]
        assert audit_candidates, "expected FUNC_AUDIT_LIST candidate"
        assert audit_candidates[0].candidate_status == "pending_review"

        denied = service.invoke_skill(
            "tenant.policy.evaluate",
            {
                "capability_id": "audit.list",
                "surface": "webui",
                "role": "ROLE_SYSTEM",
                "role_code": "ROLE_BUSIAUDIT",
                "actor_snapshot": {
                    "subject": "iaf-sub-a",
                    "tenant_id": "sd-default",
                    "org_code": "ORG-A",
                    "status": "active",
                    "role_codes": ["ROLE_BUSIAUDIT"],
                },
            },
        )
        assert denied["allowed"] is False
        assert denied["decision_reason"] == "missing_tenant_policy"

        reviewed = service.invoke_skill(
            "governance.policy_candidate.review",
            {
                "decision": "approve_and_apply",
                "items": [
                    {
                        "legacy_permission_ref": "FUNC_AUDIT_LIST",
                        "capability_id": "audit.list",
                        "legacy_system": audit_candidates[0].legacy_system,
                    }
                ],
                "role": "ROLE_SYSTEM",
                "confirmed": True,
            },
        )
        assert reviewed["audit_id"]
        assert reviewed["result"]["summary"]["applied_policy_count"] == 1

        allowed = service.invoke_skill(
            "tenant.policy.evaluate",
            {
                "capability_id": "audit.list",
                "surface": "webui",
                "role": "ROLE_SYSTEM",
                "role_code": "ROLE_BUSIAUDIT",
                "actor_snapshot": {
                    "subject": "iaf-sub-a",
                    "tenant_id": "sd-default",
                    "org_code": "ORG-A",
                    "status": "active",
                    "role_codes": ["ROLE_BUSIAUDIT"],
                },
            },
        )
        assert allowed["allowed"] is True
        assert allowed["source"] == "tenant_capability_policy"

        listed = service.invoke_skill(
            "governance.policy_candidate.list",
            {"candidate_status": "approved", "role": "ROLE_SYSTEM"},
        )
        assert listed["summary"]["total"] >= 1
        assert listed["export_report"]["total"] >= 1


def test_pipeline_reimport_is_idempotent_for_bindings_and_candidates() -> None:
    with TemporaryDirectory() as tmp:
        _bootstrap_service(tmp)
        _import_pipeline_dump(tmp, dry_run=False)
        gov = GovernanceProjectionRepository()
        bindings_before = len(gov.list_actor_org_role_bindings(tenant_id="sd-default", binding_status="active"))
        candidates_before = len(gov.list_policy_candidates(tenant_id="sd-default"))

        _import_pipeline_dump(tmp, dry_run=False)
        bindings_after = len(gov.list_actor_org_role_bindings(tenant_id="sd-default", binding_status="active"))
        candidates_after = len(gov.list_policy_candidates(tenant_id="sd-default"))

        assert bindings_after == bindings_before
        assert candidates_after == candidates_before


def test_iam_missing_actor_fail_closed_on_policy_evaluate() -> None:
    with TemporaryDirectory() as tmp:
        service, gov = _bootstrap_service(tmp)
        _import_pipeline_dump(tmp, dry_run=False)
        missing = next(item for item in gov.list_actors(tenant_id="sd-default") if item.external_actor_id == "U003")
        assert missing.status == "iam_account_missing"

        decision = service.invoke_skill(
            "tenant.policy.evaluate",
            {
                "capability_id": "audit.list",
                "surface": "webui",
                "role": "ROLE_SYSTEM",
                "role_code": "ROLE_BUSIAUDIT",
                "actor_snapshot": {
                    "subject": missing.external_actor_id,
                    "tenant_id": "sd-default",
                    "status": "iam_account_missing",
                    "role_codes": [],
                },
            },
        )
        assert decision["allowed"] is False
        assert decision["decision_reason"] in {"iam_account_missing", "actor_unmatched", "missing_tenant_policy"}


# R-002 regression — pub_resource source rows must be counted as `handled` so strict
# table_accounting doesn't fail-close `customer_acceptance_up.sh dry_run` on
# "unaccounted source row table(s): dsp_bsp.pub_resource". Existing pipeline dump
# uses pub_role_function/pub_function for ACL; pub_resource/pub_role_resource exercise
# a separate `_import_pub_role_permission_candidates(permission_kind="resource")` branch
# that previously bumped only the relation table, leaving each object row unaccounted.
_PUB_RESOURCE_ACCOUNTING_DUMP_SUFFIX = """
DROP TABLE IF EXISTS `pub_resource`;
CREATE TABLE `pub_resource` (
  `ID` varchar(36) NOT NULL,
  `CODE` varchar(64) NOT NULL,
  `NAME` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`ID`)
) ENGINE=InnoDB;

INSERT INTO `pub_resource` VALUES \
('RES-001','AUDIT_LIST','审计列表资源'),\
('RES-002','AUDIT_DETAIL','审计详情资源');

DROP TABLE IF EXISTS `pub_role_resource`;
CREATE TABLE `pub_role_resource` (
  `ROLE_CODE` varchar(64) NOT NULL,
  `RES_CODE` varchar(64) NOT NULL
) ENGINE=InnoDB;

INSERT INTO `pub_role_resource` VALUES \
('ROLE_BUSIAUDIT','AUDIT_LIST'),\
('ROLE_BUSIAUDIT','AUDIT_DETAIL');
"""


def test_pub_resource_rows_count_as_handled_for_strict_table_accounting() -> None:
    """R-002 — 每个 pub_resource 源行必须 bump 到 stats.counts["pub_resource.attached"]，
    否则 strict mode 下 run_legacy_migration 计算的 unaccounted_rows>0 会 fail-close
    `customer_acceptance_up.sh dry_run`（实际客户演练时被这条挡住过）。"""
    with TemporaryDirectory() as tmp:
        dumps_dir = Path(tmp) / "dumps"
        dumps_dir.mkdir(parents=True, exist_ok=True)
        dump_path = dumps_dir / "dump-dsp_bsp-20260523-pub-resource-e2e.sql"
        dump_path.write_text(
            _PUB_BATCH_GOVERNANCE_DUMP + _PIPELINE_DUMP_SUFFIX + _PUB_RESOURCE_ACCOUNTING_DUMP_SUFFIX,
            encoding="utf-8",
        )

        from zw_brain.adapters.legacy.mappers.governance import GovernanceMapper

        stats = GovernanceMapper().import_dump(dump_path, dry_run=True).to_dict()

        # source_counts 来自 dump 解析：刚塞 2 行
        assert stats["source_counts"].get("pub_resource") == 2, stats["source_counts"]
        # _handled_table_totals 只识别 {imported, errors, attached, merged} 4 种 kind；
        # 修复点正是给 pub_resource 每行 bump "attached"，所以 .attached 必须 == source_rows
        attached = stats["counts"].get("pub_resource.attached", 0)
        assert attached == 2, (
            f"pub_resource.attached={attached}，缺失会让 run_legacy_migration 的 "
            f"strict table_accounting 把 pub_resource 计入 unaccounted_rows 并 fail-close。"
            f" counts={stats['counts']}"
        )
