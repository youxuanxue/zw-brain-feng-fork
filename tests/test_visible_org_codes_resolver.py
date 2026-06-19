"""部门数据可见域解析器单测（M2）：ReferenceService.visible_org_codes / org_in_scope
+ GovernanceProjectionRepository.list_org_children。

锁定三态契约（None=全局 / 集=部门 / 空集=fail-closed）、下级前向兼容（父子树填充后
管理员自动见子机构、操作员不见）、owner 名/码归一成员判定（债
legacy-catalog-owner-org-name-mismatch）。这是 M4–M8 各消费面收口共同依赖的地基。
"""

from __future__ import annotations

import pytest

from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
from zw_brain.domain.services.reference_service import ReferenceService
from zw_brain.shared.migrate import ensure_runtime_schema

TENANT = "sd-default"
ORG_PARENT = "11370000MB284651XL"   # 本机构（管理员所属）
ORG_CHILD = "360002222211"          # 下级机构（parent = ORG_PARENT）
ORG_GRANDCHILD = "11360000014501340W"  # 下下级（parent = ORG_CHILD），证明递归
ORG_OTHER = "36010000876"           # 无关机构
ORG_NAME_PARENT = "省大数据局"        # 名作 owner 的 legacy 形态
DUP_NAME = "综合服务中心"            # 两机构重名 → 归一 fail-closed

MANAGER = "ROLE_ORGAN_MANAGER"
OPERATER = "ROLE_ORGAN_OPERATER"
BUSIAUDIT = "ROLE_BUSIAUDIT"
SYSTEM = "ROLE_SYSTEM"
SECURITY_AUDIT = "ROLE_SECURITY_AUDIT"


@pytest.fixture()
def temp_db() -> None:
    # Per-test isolation is provided by the conftest autouse fixture (a fresh
    # empty PG clone via ZW_BRAIN_DATABASE_URL); just ensure the schema is built.
    ensure_runtime_schema()


def _seed_flat() -> None:
    """平表（无父子）—— 复现当前真库 parent_org_code 全空。"""
    gov = GovernanceProjectionRepository()
    gov.upsert_org({"org_code": ORG_PARENT, "org_name": ORG_NAME_PARENT}, tenant_id=TENANT)
    gov.upsert_org({"org_code": ORG_OTHER, "org_name": "别家单位"}, tenant_id=TENANT)
    gov.upsert_org({"org_code": "dup-a", "org_name": DUP_NAME}, tenant_id=TENANT)
    gov.upsert_org({"org_code": "dup-b", "org_name": DUP_NAME}, tenant_id=TENANT)


def _seed_tree() -> None:
    """植入父子树 —— 证明 pub_organ_tree.PARENT_CODE 填充后下级自动展开（零代码改动）。"""
    gov = GovernanceProjectionRepository()
    gov.upsert_org({"org_code": ORG_PARENT, "org_name": ORG_NAME_PARENT}, tenant_id=TENANT)
    gov.upsert_org({"org_code": ORG_CHILD, "org_name": "下级局", "parent_org_code": ORG_PARENT}, tenant_id=TENANT)
    gov.upsert_org(
        {"org_code": ORG_GRANDCHILD, "org_name": "下下级所", "parent_org_code": ORG_CHILD}, tenant_id=TENANT
    )
    gov.upsert_org({"org_code": ORG_OTHER, "org_name": "无关机构"}, tenant_id=TENANT)


# ── 三态契约 ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("role", [BUSIAUDIT, SYSTEM, SECURITY_AUDIT])
def test_global_roles_return_none(temp_db: None, role: str) -> None:
    _seed_flat()
    assert ReferenceService().visible_org_codes(ORG_PARENT, role, tenant_id=TENANT) is None
    # 全局角色即便无 org 也是 None（不限定）。
    assert ReferenceService().visible_org_codes("", role, tenant_id=TENANT) is None


def test_dept_roles_with_org_flat_tree_return_self_only(temp_db: None) -> None:
    _seed_flat()
    ref = ReferenceService()
    assert ref.visible_org_codes(ORG_PARENT, MANAGER, tenant_id=TENANT) == {ORG_PARENT}
    assert ref.visible_org_codes(ORG_PARENT, OPERATER, tenant_id=TENANT) == {ORG_PARENT}


@pytest.mark.parametrize("role", [MANAGER, OPERATER])
def test_dept_roles_without_org_fail_closed_empty_set(temp_db: None, role: str) -> None:
    _seed_flat()
    assert ReferenceService().visible_org_codes("", role, tenant_id=TENANT) == set()


def test_unknown_role_least_privilege_self_only(temp_db: None) -> None:
    _seed_flat()
    # 未知角色按最小权限当部门角色：有 org → 仅本机构（无下级）；无 org → fail-closed。
    ref = ReferenceService()
    assert ref.visible_org_codes(ORG_PARENT, "ROLE_MYSTERY", tenant_id=TENANT) == {ORG_PARENT}
    assert ref.visible_org_codes("", "ROLE_MYSTERY", tenant_id=TENANT) == set()


# ── 下级前向兼容 ──────────────────────────────────────────────────────────────
def test_manager_sees_subtree_when_hierarchy_populated(temp_db: None) -> None:
    _seed_tree()
    visible = ReferenceService().visible_org_codes(ORG_PARENT, MANAGER, tenant_id=TENANT)
    # 管理员见本机构 + 直接下级 + 递归下下级。
    assert visible == {ORG_PARENT, ORG_CHILD, ORG_GRANDCHILD}
    assert ORG_OTHER not in visible


def test_operater_never_sees_subtree(temp_db: None) -> None:
    _seed_tree()
    # 操作员仅本机构，即使父子树已填充也不含下级。
    assert ReferenceService().visible_org_codes(ORG_PARENT, OPERATER, tenant_id=TENANT) == {ORG_PARENT}


def test_list_org_children_flat_vs_tree(temp_db: None) -> None:
    _seed_flat()
    gov = GovernanceProjectionRepository()
    assert gov.list_org_children(ORG_PARENT, tenant_id=TENANT) == []  # 平表无子
    _seed_tree()
    kids = [r.org_code for r in gov.list_org_children(ORG_PARENT, tenant_id=TENANT)]
    assert kids == [ORG_CHILD]
    assert gov.list_org_children("", tenant_id=TENANT) == []


# ── 行级成员判定 org_in_scope（名/码归一）──────────────────────────────────────
def test_org_in_scope_none_and_empty(temp_db: None) -> None:
    _seed_flat()
    ref = ReferenceService()
    assert ref.org_in_scope(ORG_OTHER, None, tenant_id=TENANT) is True   # 全局放行
    assert ref.org_in_scope(ORG_PARENT, set(), tenant_id=TENANT) is False  # fail-closed


def test_org_in_scope_code_fast_path(temp_db: None) -> None:
    _seed_flat()
    ref = ReferenceService()
    visible = {ORG_PARENT}
    assert ref.org_in_scope(ORG_PARENT, visible, tenant_id=TENANT) is True
    assert ref.org_in_scope(ORG_OTHER, visible, tenant_id=TENANT) is False


def test_org_in_scope_legacy_name_normalized_to_code(temp_db: None) -> None:
    _seed_flat()
    ref = ReferenceService()
    visible = {ORG_PARENT}  # 集合存的是码
    # 行 owner 存机构名（legacy 形态）→ 归一到码后命中。
    assert ref.org_in_scope(ORG_NAME_PARENT, visible, tenant_id=TENANT) is True


def test_org_in_scope_ambiguous_name_fail_closed(temp_db: None) -> None:
    _seed_flat()
    ref = ReferenceService()
    # 重名机构名无法唯一归一 → resolve 返 None → 不放行（fail-closed，不擅自取一条）。
    assert ref.org_in_scope(DUP_NAME, {"dup-a"}, tenant_id=TENANT) is False
