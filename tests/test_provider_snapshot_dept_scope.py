"""供数面部门数据可见域收口单测（M4，slice A1）：provider_snapshot_projection 四个
内层投影函数按 owner_org_id 收口本机构(+下级)。

锁定：
  - visible_org_codes={orgA} → catalogs/resources/api_services/inbox(field_decisions,
    hookup_reviews) 仅 orgA 行；
  - visible_org_codes=None → 全量放行（全局角色直通）；
  - visible_org_codes=set() → 空（fail-closed）；
  - publish_queue 不按部门收口（平台级发布待办，BUSIAUDIT 全局）；
  - legacy owner 存机构**名**（非码）仍按 org_in_scope 名/码归一正确保留。

temp_db 模式同 test_visible_org_codes_resolver.py；seed 同 test_provider_snapshot_projection.py。
"""

from __future__ import annotations

import pytest

from zw_brain.domain.provider_snapshot_projection import (
    enrich_provider_snapshot,
    project_api_services,
    project_provider_catalogs,
    project_provider_inbox,
    project_provider_resources,
)
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
from zw_brain.domain.repositories.resource_api import ResourceApiRepository
from zw_brain.domain.repositories.supply_demand import SupplyDemandRepository
from zw_brain.shared import db as db_module
from zw_brain.shared.migrate import ensure_runtime_schema

TENANT = "sd-default"
ORG_A = "11370000MB284651XL"   # 本机构（管理员所属）
ORG_A_NAME = "省大数据局"       # ORG_A 的机构中文名（legacy 名作 owner 形态）
ORG_B = "360002222211"         # 别家机构


@pytest.fixture()
def temp_db():
    """Fresh, migrated per-test DB. The autouse conftest fixture already supplies an
    isolated empty PostgreSQL clone; here we just ensure runtime tables are present."""
    db_module.reset_engine_cache()
    ensure_runtime_schema()
    try:
        yield
    finally:
        db_module.reset_engine_cache()


def _seed() -> None:
    """两机构各自拥有目录 / 资源 / API 服务 / 反向草稿 / 挂接待审 + 一条平台级待发布目录。"""
    gov = GovernanceProjectionRepository()
    gov.upsert_org({"org_code": ORG_A, "org_name": ORG_A_NAME}, tenant_id=TENANT)
    gov.upsert_org({"org_code": ORG_B, "org_name": "别家单位"}, tenant_id=TENANT)

    cat = CatalogRepository()
    # 目录：orgA 持码、orgB 持码（active → 进目录管理清单）。
    cat.upsert_from_resource(
        {"id": "cat-a-001", "name": "orgA 目录", "status": "active", "provider": ORG_A},
        tenant_id=TENANT,
    )
    cat.upsert_from_resource(
        {"id": "cat-b-001", "name": "orgB 目录", "status": "active", "provider": ORG_B},
        tenant_id=TENANT,
    )
    # legacy 形态：orgA 的目录 owner 存机构**名**（非码），证明 org_in_scope 名/码归一。
    cat.upsert_from_resource(
        {"id": "cat-a-legacy-name", "name": "orgA 存量目录（名作 owner）", "status": "active", "provider": ORG_A_NAME},
        tenant_id=TENANT,
    )
    # 反向编目待审草稿（field_decisions 收件箱口径：source=reverse ∧ lifecycle=draft）。
    cat.upsert_from_resource(
        {"id": "rev-a-001", "name": "orgA 反向草稿", "status": "draft", "source": "reverse", "provider": ORG_A},
        tenant_id=TENANT,
    )
    cat.upsert_from_resource(
        {"id": "rev-b-001", "name": "orgB 反向草稿", "status": "draft", "source": "reverse", "provider": ORG_B},
        tenant_id=TENANT,
    )
    # 待发布目录（publish_queue）：平台级发布待办，各机构各一条 —— 不应被部门收口。
    cat.upsert_from_resource(
        {"id": "pub-a-001", "name": "orgA 待发布", "status": "approved_pending_publish", "provider": ORG_A},
        tenant_id=TENANT,
    )
    cat.upsert_from_resource(
        {"id": "pub-b-001", "name": "orgB 待发布", "status": "approved_pending_publish", "provider": ORG_B},
        tenant_id=TENANT,
    )

    res = ResourceApiRepository()
    # 资源（库表，进资源管理清单 + 挂接审核收件箱）。
    res.upsert_asset(
        {
            "resource_code": "res-a-001",
            "title": "orgA 库表资源",
            "resource_kind": "table",
            "lifecycle_status": "pending_review",
            "owner_org_id": ORG_A,
        },
        tenant_id=TENANT,
    )
    res.upsert_asset(
        {
            "resource_code": "res-b-001",
            "title": "orgB 库表资源",
            "resource_kind": "table",
            "lifecycle_status": "pending_review",
            "owner_org_id": ORG_B,
        },
        tenant_id=TENANT,
    )
    # API 服务（resource_kind=api → project_api_services）。
    res.upsert_asset(
        {
            "resource_code": "api-a-001",
            "title": "orgA 代理服务",
            "resource_kind": "api",
            "lifecycle_status": "active",
            "owner_org_id": ORG_A,
        },
        tenant_id=TENANT,
    )
    res.upsert_asset(
        {
            "resource_code": "api-b-001",
            "title": "orgB 代理服务",
            "resource_kind": "api",
            "lifecycle_status": "active",
            "owner_org_id": ORG_B,
        },
        tenant_id=TENANT,
    )


# ── 1. 集 → 仅 orgA 行 ─────────────────────────────────────────────────────────
def test_catalogs_scoped_to_org_a(temp_db) -> None:
    _seed()
    codes = {c["catalog_code"] for c in project_provider_catalogs(tenant_id=TENANT, visible_org_codes={ORG_A})}
    assert "cat-a-001" in codes
    assert "cat-a-legacy-name" in codes  # 名作 owner 也归一保留（见专项断言）
    assert "cat-b-001" not in codes


def test_resources_scoped_to_org_a(temp_db) -> None:
    _seed()
    ids = {r["id"] for r in project_provider_resources(tenant_id=TENANT, visible_org_codes={ORG_A})}
    assert "res-a-001" in ids
    assert "res-b-001" not in ids


def test_api_services_scoped_to_org_a(temp_db) -> None:
    _seed()
    ids = {s["id"] for s in project_api_services(tenant_id=TENANT, visible_org_codes={ORG_A})}
    assert "api-a-001" in ids
    assert "api-b-001" not in ids


def test_inbox_field_decisions_and_hookups_scoped_to_org_a(temp_db) -> None:
    _seed()
    inbox = project_provider_inbox(tenant_id=TENANT, visible_org_codes={ORG_A})
    field_ids = {r["id"] for r in inbox["field_decisions"]}
    hookup_ids = {r["id"] for r in inbox["hookup_reviews"]}
    assert field_ids == {"rev-a-001"}
    assert hookup_ids == {"res-a-001"}
    assert "rev-b-001" not in field_ids
    assert "res-b-001" not in hookup_ids


def test_inbox_demand_matches_scoped_by_target_provider_org(temp_db) -> None:
    _seed()
    supply = SupplyDemandRepository()
    supply.register_demand(
        demand_id="dem-target-org-a",
        title="不动产交易信息共享",
        applicant="u-demo",
        applicant_dept="申请部门",
        tenant_id=TENANT,
        target_resource_hint="不动产登记",
        target_org_code=ORG_A,
    )
    supply.register_demand(
        demand_id="dem-target-org-b",
        title="别家部门需求",
        applicant="u-demo",
        applicant_dept="申请部门",
        tenant_id=TENANT,
        target_resource_hint="别家资源",
        target_org_code=ORG_B,
    )
    supply.register_demand(
        demand_id="dem-legacy-no-target",
        title="历史无目标部门需求",
        applicant="u-demo",
        applicant_dept="申请部门",
        tenant_id=TENANT,
    )

    scoped_a = project_provider_inbox(tenant_id=TENANT, visible_org_codes={ORG_A})
    ids_a = {r["id"] for r in scoped_a["demand_matches"]}
    assert "dem-target-org-a" in ids_a
    assert "dem-target-org-b" not in ids_a
    assert "dem-legacy-no-target" in ids_a

    global_view = project_provider_inbox(tenant_id=TENANT, visible_org_codes=None)
    global_ids = {r["id"] for r in global_view["demand_matches"]}
    assert {"dem-target-org-a", "dem-target-org-b", "dem-legacy-no-target"} <= global_ids

    fail_closed = project_provider_inbox(tenant_id=TENANT, visible_org_codes=set())
    fail_closed_ids = {r["id"] for r in fail_closed["demand_matches"]}
    assert fail_closed_ids == set()


# ── 2. None → 全量放行 ─────────────────────────────────────────────────────────
def test_none_passes_through_all_rows(temp_db) -> None:
    _seed()
    cat_codes = {c["catalog_code"] for c in project_provider_catalogs(tenant_id=TENANT, visible_org_codes=None)}
    res_ids = {r["id"] for r in project_provider_resources(tenant_id=TENANT, visible_org_codes=None)}
    api_ids = {s["id"] for s in project_api_services(tenant_id=TENANT, visible_org_codes=None)}
    inbox = project_provider_inbox(tenant_id=TENANT, visible_org_codes=None)
    field_ids = {r["id"] for r in inbox["field_decisions"]}
    hookup_ids = {r["id"] for r in inbox["hookup_reviews"]}

    assert {"cat-a-001", "cat-b-001", "cat-a-legacy-name"} <= cat_codes
    assert {"res-a-001", "res-b-001"} <= res_ids
    assert {"api-a-001", "api-b-001"} <= api_ids
    assert field_ids == {"rev-a-001", "rev-b-001"}
    assert hookup_ids == {"res-a-001", "res-b-001"}


# ── 3. 空集 → fail-closed（全部丢弃）──────────────────────────────────────────
def test_empty_set_fail_closed_drops_all(temp_db) -> None:
    _seed()
    assert project_provider_catalogs(tenant_id=TENANT, visible_org_codes=set()) == []
    assert project_provider_resources(tenant_id=TENANT, visible_org_codes=set()) == []
    assert project_api_services(tenant_id=TENANT, visible_org_codes=set()) == []
    inbox = project_provider_inbox(tenant_id=TENANT, visible_org_codes=set())
    assert inbox["field_decisions"] == []
    assert inbox["hookup_reviews"] == []


# ── 4. publish_queue 不按部门收口 ─────────────────────────────────────────────
def test_publish_queue_not_dept_filtered(temp_db) -> None:
    _seed()
    # 即便收口到 orgA，待发布平台级待办仍含两机构（不被部门过滤）。
    scoped = project_provider_inbox(tenant_id=TENANT, visible_org_codes={ORG_A})
    scoped_pub = {r["id"] for r in scoped["publish_queue"]}
    assert {"pub-a-001", "pub-b-001"} <= scoped_pub
    # 空集 fail-closed 也不影响 publish_queue（与 field_decisions/hookup_reviews 形成对照）。
    fail_closed = project_provider_inbox(tenant_id=TENANT, visible_org_codes=set())
    fc_pub = {r["id"] for r in fail_closed["publish_queue"]}
    assert {"pub-a-001", "pub-b-001"} <= fc_pub


# ── 5. legacy owner 存机构名（非码）→ 归一后仍保留 ─────────────────────────────
def test_legacy_name_owner_catalog_kept_when_org_in_scope(temp_db) -> None:
    _seed()
    # cat-a-legacy-name 的 owner 存机构**名** ORG_A_NAME，可见集存的是**码** ORG_A；
    # org_in_scope 名/码归一后该行应保留（证明归一生效，非裸字符串比对漏判）。
    codes = {c["catalog_code"] for c in project_provider_catalogs(tenant_id=TENANT, visible_org_codes={ORG_A})}
    assert "cat-a-legacy-name" in codes
    # 反证：若收口到 orgB，名作 owner 的 orgA 目录不得串台进 orgB 可见域。
    codes_b = {c["catalog_code"] for c in project_provider_catalogs(tenant_id=TENANT, visible_org_codes={ORG_B})}
    assert "cat-a-legacy-name" not in codes_b


# ── R-001（xj-review #294）：enrich 层 fail-closed 不回落 seed 演示视图 ──────────────
# enrich_provider_snapshot 有 replace-when-DB-nonempty 回落（live 空 → 保留 seed.provider.catalogs）。
# 部门收口下 live 空（fail-closed 空集 / 零目录部门）必须给**权威空**，绝不回落 seed 演示目录——
# 否则破坏隔离 + 违 D47 演示诚实化。下列两测锁定：部门收口空→[]，全局空库→保留 seed（不回归）。
_SEED_PROVIDER = {
    "provider": {
        "catalogs": [{"id": "seed-cat", "catalog_code": "seed-cat", "name": "演示目录", "owner_org_id": ORG_B}],
        "resources": [{"id": "seed-res", "name": "演示资源", "owner_org_id": ORG_B}],
    }
}


def test_enrich_provider_fail_closed_does_not_fall_back_to_seed(temp_db) -> None:
    import copy as _copy

    out = enrich_provider_snapshot(_copy.deepcopy(_SEED_PROVIDER), tenant_id=TENANT, visible_org_codes=set())
    assert out["provider"]["catalogs"] == [], "fail-closed（空集）不回落 seed 演示目录"
    assert out["provider"]["resources"] == [], "fail-closed（空集）不回落 seed 演示资源"


def test_enrich_provider_dept_with_no_owned_rows_is_authoritative_empty(temp_db) -> None:
    import copy as _copy

    # 部门收口到一个本库无任何目录的机构 → live 空 → 权威空（不回落 seed）。
    out = enrich_provider_snapshot(_copy.deepcopy(_SEED_PROVIDER), tenant_id=TENANT, visible_org_codes={ORG_A})
    assert out["provider"]["catalogs"] == [], "零目录部门=权威空，不漏看 seed 演示目录"
    assert out["provider"]["resources"] == []


def test_enrich_provider_global_empty_db_still_keeps_seed(temp_db) -> None:
    import copy as _copy

    # 对照（不回归）：全局视角 visible=None + DB 空 → 保留 seed 视图（既有 replace-when-nonempty 行为）。
    out = enrich_provider_snapshot(_copy.deepcopy(_SEED_PROVIDER), tenant_id=TENANT, visible_org_codes=None)
    assert {c["id"] for c in out["provider"]["catalogs"]} == {"seed-cat"}, "全局空库保留 seed（不回归）"
    assert {r["id"] for r in out["provider"]["resources"]} == {"seed-res"}
