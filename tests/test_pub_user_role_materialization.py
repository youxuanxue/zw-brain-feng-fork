"""D63：pub_user_role 作为产品角色主源之一被 materialize（合成 dump，真 GovernanceMapper）。

根因——旧导入器只把 organ_role 喂给角色映射、pub_user_role 仅 stats.bump 不落 binding，
致重导入丢掉旧平台真实角色（生产实测 60% 有角色用户被判错）。本测固化修复行为：
  ① 仅 pub_user_role 有角色的用户也拿到 binding（join 按 pub_user.ID，避开 USER_CODE='0' 漏配）
  ② ROLE_SUPER→ROLE_SYSTEM（已签）+ system_role_from_user_role 复核信号
  ③ 跨多 APP 域 union + 与 organ_role 合并去重
  ④ 无 sub → 仍 fail-closed（iam_account_missing / 0 binding）
  ⑤ 重导入幂等
"""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
from zw_brain.shared import audit as audit_bus
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.migrate import ensure_runtime_schema

# U001 故意令 pub_user.USER_CODE='0'（真实生产 493/710 行如此），而 pub_user_role.USER_CODE='U001'
# (= pub_user.ID)。证明 pub_user_role 按 ID join、不被 '0' 漏配（organ_role 历史 key-miss 不复发）。
# U001 无 organ_role → 仅靠 pub_user_role 拿角色（修复点）。
# U002 ROLE_SUPER → ROLE_SYSTEM + 复核信号。
# U003 organ(OPERATER) ∪ pub_user_role(MANAGER@DSP, BUSIAUDIT@GDRP) → 三角色合并 + 跨 app union。
# U004 有 pub_user_role 角色但无 sub → fail-closed。
_DUMP = """\
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
('U001','user_a','用户A','0',NULL,NULL,'ORG-A','1'),\
('U002','user_super','超管B','0',NULL,NULL,'ORG-A','1'),\
('U003','user_c','用户C','U003',NULL,NULL,'ORG-A','1'),\
('U004','user_nosub','无绑定D','0',NULL,NULL,'ORG-A','1');

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
('UOR3','ORG-A','ROLE_ORGAN_OPERATER','U003','1');

DROP TABLE IF EXISTS `pub_user_role`;
CREATE TABLE `pub_user_role` (
  `ROLE_CODE` varchar(36) NOT NULL,
  `USER_CODE` varchar(36) NOT NULL,
  `APP_CODE` varchar(36) NOT NULL,
  `HMAC` varchar(5000) DEFAULT NULL,
  PRIMARY KEY (`ROLE_CODE`,`USER_CODE`,`APP_CODE`)
) ENGINE=InnoDB;

INSERT INTO `pub_user_role` VALUES \
('ROLE_BUSIAUDIT','U001','DSP-CATALOG',NULL),\
('ROLE_SUPER','U002','GDRP-BACK-SYSTEM',NULL),\
('ROLE_ORGAN_MANAGER','U003','DSP-CATALOG',NULL),\
('ROLE_BUSIAUDIT','U003','GDRP-BACK-SYSTEM',NULL),\
('ROLE_ORGAN_MANAGER','U004','DSP-CATALOG',NULL);

DROP TABLE IF EXISTS `iaf_binding_manifest`;
CREATE TABLE `iaf_binding_manifest` (
  `LEGACY_USER_ID` varchar(36) NOT NULL,
  `LEGACY_USER_CODE` varchar(36) DEFAULT NULL,
  `IAF_SUB` varchar(128) NOT NULL
) ENGINE=InnoDB;

INSERT INTO `iaf_binding_manifest` VALUES \
('U001','U001','iaf-real-1'),\
('U002','U002','iaf-real-2'),\
('U003','U003','iaf-real-3');

DROP TABLE IF EXISTS `role_mapping_manifest`;
CREATE TABLE `role_mapping_manifest` (
  `LEGACY_ROLE_REF` varchar(128) NOT NULL,
  `TARGET_TYPE` varchar(16) NOT NULL,
  `TARGET_ROLE_CODE` varchar(64) DEFAULT NULL,
  `TARGET_TAG` varchar(64) DEFAULT NULL
) ENGINE=InnoDB;

INSERT INTO `role_mapping_manifest` VALUES \
('ROLE_BUSIAUDIT','role','ROLE_BUSIAUDIT',NULL),\
('ROLE_ORGAN_MANAGER','role','ROLE_ORGAN_MANAGER',NULL),\
('ROLE_ORGAN_OPERATER','role','ROLE_ORGAN_OPERATER',NULL),\
('ROLE_SUPER','role','ROLE_SYSTEM',NULL);
"""


def _bootstrap(tmp: Path) -> GovernanceProjectionRepository:
    # The autouse conftest fixture supplies a fresh, migrated per-test PG clone; the
    # temp dir below is only the on-disk staging area for the legacy dump file.
    os.environ.setdefault("ZW_BRAIN_INFERENCE_MODE", "mock")
    ensure_runtime_schema()
    audit_bus.configure_sink(DatabaseStore().append_audit_event)
    return GovernanceProjectionRepository()


def _import(tmp: Path, *, dry_run: bool = False) -> dict:
    dumps = tmp / "dumps"
    dumps.mkdir(parents=True, exist_ok=True)
    path = dumps / "dump-dsp_bsp-20260619-d63.sql"
    path.write_text(_DUMP, encoding="utf-8")
    from zw_brain.adapters.legacy.mappers.governance import GovernanceMapper

    return GovernanceMapper().import_dump(path, dry_run=dry_run).to_dict()


def _roles_by_account(gov: GovernanceProjectionRepository) -> dict[str, set[str]]:
    actors = gov.list_actors(tenant_id="sd-default")
    binds = gov.list_actor_org_role_bindings(tenant_id="sd-default", binding_status="active")
    by_aid: dict[str, set[str]] = {}
    for b in binds:
        by_aid.setdefault(b.external_actor_id, set()).add(b.role_code)
    import json

    out: dict[str, set[str]] = {}
    for a in actors:
        pj = a.profile_json if isinstance(a.profile_json, dict) else (json.loads(a.profile_json) if a.profile_json else {})
        out[pj.get("account") or a.external_actor_id] = by_aid.get(a.external_actor_id, set())
    return out


def test_pub_user_role_only_user_gets_binding_join_by_id() -> None:
    """U001：无 organ_role、pub_user.USER_CODE='0'，仅 pub_user_role 有角色 → 仍拿到 binding。"""
    with TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        gov = _bootstrap(tmp)
        _import(tmp)
        roles = _roles_by_account(gov)
        assert roles.get("user_a") == {"ROLE_BUSIAUDIT"}, roles.get("user_a")


def test_role_super_maps_to_system_with_review_signal() -> None:
    """U002：ROLE_SUPER → ROLE_SYSTEM（已签）+ system_role_from_user_role 复核 issue。"""
    with TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        gov = _bootstrap(tmp)
        stats = _import(tmp)
        roles = _roles_by_account(gov)
        assert roles.get("user_super") == {"ROLE_SYSTEM"}, roles.get("user_super")
        sys_signals = [i for i in stats["issues"] if i.get("type") == "system_role_from_user_role"]
        assert any(i.get("legacy_ref") == "U002" for i in sys_signals), sys_signals


def test_organ_union_pub_user_role_across_apps() -> None:
    """U003：organ(OPERATER) ∪ pub_user_role(MANAGER@DSP, BUSIAUDIT@GDRP) → 三角色合并去重。"""
    with TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        gov = _bootstrap(tmp)
        _import(tmp)
        roles = _roles_by_account(gov)
        assert roles.get("user_c") == {
            "ROLE_ORGAN_OPERATER",
            "ROLE_ORGAN_MANAGER",
            "ROLE_BUSIAUDIT",
        }, roles.get("user_c")


def test_pub_user_role_without_sub_fail_closed() -> None:
    """U004：有 pub_user_role 角色但无 iaf_sub → iam_account_missing、0 binding（gate 仍关）。"""
    with TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        gov = _bootstrap(tmp)
        _import(tmp)
        roles = _roles_by_account(gov)
        assert roles.get("user_nosub") == set(), roles.get("user_nosub")
        actors = gov.list_actors(tenant_id="sd-default")
        u4 = next(a for a in actors if (a.display_name or "") == "无绑定D")
        assert u4.status == "iam_account_missing", u4.status


def test_pub_user_role_materialization_is_idempotent() -> None:
    """重导入幂等：binding 总数不随次数累积。"""
    with TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        gov = _bootstrap(tmp)
        _import(tmp)
        before = len(gov.list_actor_org_role_bindings(tenant_id="sd-default", binding_status="active"))
        _import(tmp)
        after = len(gov.list_actor_org_role_bindings(tenant_id="sd-default", binding_status="active"))
        assert before == after, (before, after)
        # 实证总量：U001(1)+U002(1)+U003(3)=5 条 active binding（U004 无 sub 不计）
        assert before == 5, before
