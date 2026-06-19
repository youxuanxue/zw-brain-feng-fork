# Wave: real-seed integration
# Journey: J1
# Pages: P2 目录浏览 → P2 目录详情（钻取链路）
# Consumer-faces: API (brain.invoke_skill)
# Roles: ROLE_ORGAN_MANAGER
# Trace:
#   zw_brain/command/handlers/j1/catalog_meta.py (catalog.browse / catalog.resource.list)
#   zw_brain/command/handlers/j1/catalog_entry.py (catalog.entry.query)
#   webui/src/views/P2CatalogBrowse.vue → P2CatalogDetail.vue → useCatalogResources.ts
#   docs/approved/zw-brain-architecture.md (D43 j1-catalog-drilldown / D42.b)
"""J1 医保目录 → 资源钻取链路的真灌库守卫（D43 / D42.b）。

把"靠手验"的钻取链路硬化成自动化门禁。断言（全部对真灌库 .data/zw_brain.db 跑）：

  1. catalog.browse 默认返回 + 翻页里，5 个医保 basic-elem 目录全部可达。
  2. 每个医保目录 catalog.entry.query({catalog_code}) → total=1 + 详情字段非空。
  3. 每个医保目录 catalog.resource.list → 诚实空态（total=0, items:[], 带 catalog 信息，
     不 raise NotFoundError/entity_not_found）—— 守住"目录有但暂无关联资源"的合法态，
     防回归成 404/422。
  4. 这些目录被 topic_package 以 ref_type=catalog_entry / ref_id=basic-elem:... 引用，
     且 ref_id 能解析回真实 catalog_entry（D42.b 引用可达）。

真灌库缺位时（worktree 隔离环境 / CI clean build）经 realistic_pg_module 优雅 skip。
D11：医保目录 catalog_code 不硬编码，由 catalog.browse 按真实 title 动态解析（守 D18）。
"""
from __future__ import annotations

import pytest

from tests._pg_realistic import realistic_pg_module  # noqa: F401  (module fixture)
from tests._trusted_payload import invoke_trusted

TENANT = "sd-default"

# 真灌库经 realistic_pg_module 克隆 zw_realistic_tmpl（含真实旧平台数据）注入
# ZW_BRAIN_DATABASE_URL；模板缺位（CI 无 dump）整模块 skip，承接旧
# require_real_seed({"catalog_entry": 100}) 跳过语义。
pytestmark = pytest.mark.usefixtures("realistic_pg_module")

# 已核实事实（D43.b）：5 个医保 basic-elem 目录已作 catalog_entry 主表实体录入真灌库。
# 用 title 集合而非硬编码 catalog_code 锚定（D11/D18），运行时从 catalog.browse 解析码。
MEDICAL_TITLES = frozenset(
    {
        "医疗救助信息",
        "医保码信息",
        "异地就医统筹区开通信息",
        "异地就医定点医疗机构信息",
        "异地就医经办机构信息",
    }
)

@pytest.fixture()
def brain():
    # function-scoped：realistic_pg_module 模块级钉住真灌库克隆，但根 conftest 的 hands-off
    # 分支仍每测试重置 audit 全局（清 sink）；故 store + 审计 sink 必须每测试对同一克隆重挂。
    import zw_brain.shared.audit as audit_bus
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore

    ds = DatabaseStore()
    audit_bus.configure_sink(ds.append_audit_event)
    return BrainService(state_store=StateStore(database_store=ds))


def _call(brain, skill_id: str, payload: dict, role: str = "ROLE_ORGAN_MANAGER") -> dict:
    out = invoke_trusted(brain, skill_id, payload, role=role)
    if isinstance(out, dict) and "result" in out and "audit_id" in out:
        return out["result"]
    return out


def _browse_all(brain) -> dict[str, str]:
    """翻完 catalog.browse 全部默认页（active real），返回 {catalog_code: title}。"""
    found: dict[str, str] = {}
    page = 1
    while True:
        res = _call(brain, "catalog.browse", {"limit": 100, "page": page})
        for item in res["items"]:
            found[item["catalog_code"]] = item["title"]
        if page * 100 >= res["total"]:
            break
        page += 1
    return found


@pytest.fixture()
def medical_codes(brain) -> dict[str, str]:
    """从 catalog.browse 动态解析 5 个医保目录的真实 catalog_code（不硬编码）。"""
    by_code = _browse_all(brain)
    resolved = {code: title for code, title in by_code.items() if title in MEDICAL_TITLES}
    return resolved


# ──────────────────────────────────────────────────────────────────────
# 1. catalog.browse 默认返回里 5 个医保目录全部可达
# ──────────────────────────────────────────────────────────────────────


def test_browse_default_reaches_all_five_medical_catalogs(medical_codes: dict[str, str]) -> None:
    """catalog.browse 默认（active/real）翻页里 5 个医保目录 title 全部可达。"""
    reached_titles = set(medical_codes.values())
    missing = MEDICAL_TITLES - reached_titles
    assert not missing, f"catalog.browse 默认返回缺失医保目录: {sorted(missing)}"
    assert len(medical_codes) == 5, (
        f"应解析出恰好 5 个医保目录，实得 {len(medical_codes)}: {medical_codes}"
    )
    # basic-elem 主表归属（D43.b）：catalog_code 形如 basic-elem:<uuid>
    for code in medical_codes:
        assert code.startswith("basic-elem:"), f"医保目录 catalog_code 应属 basic-elem 主表: {code}"


# ──────────────────────────────────────────────────────────────────────
# 2. catalog.entry.query 取单目录详情 → total=1 + 字段非空
# ──────────────────────────────────────────────────────────────────────


def test_entry_query_returns_single_detail_per_medical_catalog(
    brain, medical_codes: dict[str, str]
) -> None:
    """每个医保目录 catalog.entry.query({catalog_code}) → total=1 + title/owner 非空。"""
    assert medical_codes, "前置：必须解析到医保目录（否则 browse 链路已断）"
    for code, expected_title in medical_codes.items():
        res = _call(brain, "catalog.entry.query", {"catalog_code": code})
        assert res["total"] == 1, f"{code} 应唯一命中，实得 total={res['total']}"
        assert len(res["items"]) == 1, f"{code} items 应恰 1 条"
        detail = res["items"][0]
        assert detail["catalog_code"] == code
        assert detail["title"] == expected_title, f"{code} title 漂移: {detail['title']}"
        assert detail["title"].strip(), f"{code} title 不应为空"
        # owner（责任方机构）非空 —— 医保目录归属医保局机构编码
        assert detail.get("owner_org_id"), f"{code} owner_org_id 应非空"
        # source_ref 类血缘信息落在 summary_json（真目录条目均带 summary）
        assert isinstance(detail.get("summary_json"), dict), f"{code} summary_json 应为对象"


# ──────────────────────────────────────────────────────────────────────
# 3. catalog.resource.list 诚实空态（total=0，不 raise）
# ──────────────────────────────────────────────────────────────────────


def test_resource_list_honest_empty_for_medical_catalogs(
    brain, medical_codes: dict[str, str]
) -> None:
    """每个医保目录 catalog.resource.list → 诚实空态：total=0 + items:[] + catalog 非空，
    不 raise（守住"目录有但暂无关联资源"合法态，防回归成 404/422）。"""
    assert medical_codes, "前置：必须解析到医保目录"
    for code, expected_title in medical_codes.items():
        res = _call(brain, "catalog.resource.list", {"catalog_code": code})
        assert res["total"] == 0, f"{code} 当前应无关联资源，实得 total={res['total']}"
        assert res["items"] == [], f"{code} items 应为空列表"
        # 关键诚实性：空态仍带 catalog 详情，证明目录存在而非 not_found
        assert res["catalog"]["catalog_code"] == code
        assert res["catalog"]["title"] == expected_title


def test_resource_list_unknown_catalog_raises_not_found(brain) -> None:
    """对照组：真不存在的 catalog_code → NotFoundError，与"存在但空"语义分明。"""
    from zw_brain.command.brain import NotFoundError

    with pytest.raises(NotFoundError):
        _call(brain, "catalog.resource.list", {"catalog_code": "basic-elem:does-not-exist-xyz"})


# ──────────────────────────────────────────────────────────────────────
# 4. topic_package 对医保目录的 ref（ref_type=catalog_entry）可解析（D42.b）
# ──────────────────────────────────────────────────────────────────────


def test_topic_package_refs_to_medical_catalogs_resolve(medical_codes: dict[str, str]) -> None:
    """医保目录被 topic_package 以 ref_type=catalog_entry/ref_id=basic-elem:... 引用，
    且每个被引用的 ref_id 能解析回真实 catalog_entry（兑现 D42.b：引用目录主表可达）。"""
    from zw_brain.domain.repositories.catalog import CatalogRepository
    from zw_brain.domain.repositories.topic_package import TopicPackageRepository

    assert medical_codes, "前置：必须解析到医保目录"
    tpr = TopicPackageRepository()
    cat_repo = CatalogRepository()

    # 收集所有 topic_package 对这些医保 catalog_code 的 catalog_entry ref
    medical_code_set = set(medical_codes)
    refs_hit: set[str] = set()
    for pkg in tpr.list_packages(tenant_id=TENANT):
        for item in tpr.list_items(pkg.package_code, tenant_id=TENANT):
            if item.ref_type != "catalog_entry":
                continue
            if item.ref_id in medical_code_set:
                # ref_id 必须解析回真实 catalog_entry（不是悬空引用）
                entry = cat_repo.get_entry(item.ref_id, tenant_id=TENANT)
                assert entry is not None, f"topic_package {pkg.package_code} 引用悬空: {item.ref_id}"
                assert entry.catalog_code == item.ref_id
                refs_hit.add(item.ref_id)

    # 至少有一个医保目录被专题包引用且引用可达（D42.b 钻取链路打通的反向证据）
    assert refs_hit, "无任何 topic_package 引用医保目录主表（D42.b 引用链路缺位）"
    assert refs_hit <= medical_code_set
