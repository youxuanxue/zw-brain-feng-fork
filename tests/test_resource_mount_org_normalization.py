"""挂接跨 org 守卫的名/码归一（债 legacy-catalog-owner-org-name-mismatch 关账测试）。

根因：legacy 导入目录 owner_org_id 存机构名（「省大数据局」），资源侧用统一社会信用代码——
`_guard_catalog_same_org` 裸字符串比对把同一机构误判跨 org，真库挂接到存量目录整条路 fail-closed。
修法（读层兜底）：比对前两侧经参照主数据（org_projection）归一到码；未知/重名歧义仍拒（fail-closed 不放松）。
"""

from __future__ import annotations

import pytest

from tests._trusted_payload import invoke_trusted
from zw_brain.command.brain import BrainService
from zw_brain.domain.errors import AccessDeniedError
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
from zw_brain.domain.services.reference_service import ReferenceService
from zw_brain.shared import audit as audit_bus
from zw_brain.shared import db as db_module
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.migrate import ensure_runtime_schema
from zw_brain.shared.state_store import StateStore

TENANT = "sd-default"
ORG_CODE = "11370000MB284651XL"
ORG_NAME = "省大数据局"
ORG_OTHER_CODE = "360002222211"
ORG_OTHER_NAME = "别家单位"
DUP_NAME = "综合服务中心"  # 两机构重名 → 归一必须 fail-closed

CAT_NAME_OWNER = "cat-legacy-name-owner"   # legacy 形态：owner_org 存机构名
CAT_DUP_OWNER = "cat-dup-name-owner"       # owner_org 存重名机构名
CAT_OTHER_NAME_OWNER = "cat-other-name"    # owner_org 存别家机构名

OPERATER = "ROLE_ORGAN_OPERATER"


@pytest.fixture()
def temp_db():
    """Fresh, migrated per-test DB. The autouse conftest fixture supplies an isolated
    empty PostgreSQL clone; here we just ensure runtime tables are present."""
    db_module.reset_engine_cache()
    ensure_runtime_schema()
    yield
    db_module.reset_engine_cache()


def _seed() -> None:
    gov = GovernanceProjectionRepository()
    gov.upsert_org({"org_code": ORG_CODE, "org_name": ORG_NAME}, tenant_id=TENANT)
    gov.upsert_org({"org_code": ORG_OTHER_CODE, "org_name": ORG_OTHER_NAME}, tenant_id=TENANT)
    gov.upsert_org({"org_code": "dup-org-a", "org_name": DUP_NAME}, tenant_id=TENANT)
    gov.upsert_org({"org_code": "dup-org-b", "org_name": DUP_NAME}, tenant_id=TENANT)
    cat = CatalogRepository()
    cat.upsert_from_resource(
        {"id": CAT_NAME_OWNER, "name": "存量目录（名作 owner）", "status": "active", "provider": ORG_NAME},
        tenant_id=TENANT,
    )
    cat.upsert_from_resource(
        {"id": CAT_DUP_OWNER, "name": "存量目录（重名 owner）", "status": "active", "provider": DUP_NAME},
        tenant_id=TENANT,
    )
    cat.upsert_from_resource(
        {"id": CAT_OTHER_NAME_OWNER, "name": "别家存量目录", "status": "active", "provider": ORG_OTHER_NAME},
        tenant_id=TENANT,
    )


@pytest.fixture()
def brain(temp_db) -> BrainService:
    ds = DatabaseStore()
    ds.initialize()
    audit_bus.configure_sink(ds.append_audit_event)
    _seed()
    return BrainService(state_store=StateStore(database_store=ds))


def _file_payload(resource_code: str, *, owner: str, catalog: str) -> dict:
    return {
        "resource_code": resource_code,
        "catalog_code": catalog,
        "title": f"{resource_code} 文件",
        "owner_org_id": owner,
        "file_name": "data.csv",
        "access_path": f"/data/{resource_code}.csv",
        "content_hash": "sha256:norm",
        "update_frequency": "daily",
        "confirmed": True,
    }


# ── resolve_org_code 单元面 ────────────────────────────────────────────────

def test_resolve_code_passthrough(brain: BrainService) -> None:
    assert ReferenceService().resolve_org_code(ORG_CODE) == ORG_CODE


def test_resolve_unique_name_to_code(brain: BrainService) -> None:
    assert ReferenceService().resolve_org_code(ORG_NAME) == ORG_CODE
    assert ReferenceService().resolve_org_code(f"  {ORG_NAME}  ") == ORG_CODE


def test_resolve_ambiguous_or_unknown_is_none(brain: BrainService) -> None:
    ref = ReferenceService()
    assert ref.resolve_org_code(DUP_NAME) is None  # 重名歧义不擅自取第一条
    assert ref.resolve_org_code("不存在的单位") is None
    assert ref.resolve_org_code("") is None
    assert ref.resolve_org_code(None) is None


# ── 守卫行为面（A6 根因回归网）────────────────────────────────────────────

def test_mount_to_legacy_name_owner_catalog_passes(brain: BrainService) -> None:
    """A6 根因修复：资源持码、目录持名、同一机构 → 归一后放行。"""
    envelope = invoke_trusted(
        brain, "resource.mount.file.prepare",
        _file_payload("res-norm-ok", owner=ORG_CODE, catalog=CAT_NAME_OWNER), role=OPERATER,
    )
    assert envelope["ok"] is True
    assert envelope["result"]["resource_code"] == "res-norm-ok"
    assert envelope["result"]["catalog_code"] == CAT_NAME_OWNER


def test_mount_cross_org_name_vs_code_still_rejected(brain: BrainService) -> None:
    """真跨 org（资源持码、目录持别家机构名）→ 归一后仍不等，照拒。"""
    with pytest.raises(AccessDeniedError):
        invoke_trusted(
            brain, "resource.mount.file.prepare",
            _file_payload("res-norm-cross", owner=ORG_CODE, catalog=CAT_OTHER_NAME_OWNER), role=OPERATER,
        )


def test_mount_to_ambiguous_name_owner_rejected(brain: BrainService) -> None:
    """目录 owner 是重名机构名 → 归一歧义 → fail-closed 拒（不擅自匹配）。"""
    with pytest.raises(AccessDeniedError):
        invoke_trusted(
            brain, "resource.mount.file.prepare",
            _file_payload("res-norm-dup", owner="dup-org-a", catalog=CAT_DUP_OWNER), role=OPERATER,
        )


def test_mount_unknown_owner_value_rejected(brain: BrainService) -> None:
    """资源 owner 写了参照主数据查无的值 → 归一不出 → 照拒（守卫语义不放松）。"""
    with pytest.raises(AccessDeniedError):
        invoke_trusted(
            brain, "resource.mount.file.prepare",
            _file_payload("res-norm-unknown", owner="瞎写的单位", catalog=CAT_NAME_OWNER), role=OPERATER,
        )
