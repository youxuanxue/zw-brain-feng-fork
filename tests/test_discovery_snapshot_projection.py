"""J1 list snapshot projections — requests / approvals / discovery.resources 全量真实库投影。

D45 / 关 D43.c(1)。

enrich-direct 用例用 ``temp_db``（只建空 schema、**不**走 DatabaseStore.initialize 的参考
数据注入）→ DB 真空，自己 seed → 断言替换/排他/保留 seed 干净。data.search 用例需 service +
trust-stamp 调用，用 ``brain`` fixture（其 initialize 会注入参考资源）+ invoke_trusted。
**不依赖 .data/zw_brain.db**，CI 内可跑。
"""

from __future__ import annotations

import copy
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tests._trusted_payload import invoke_trusted
from zw_brain.command.brain import BrainService
from zw_brain.domain.discovery_snapshot_projection import (
    enrich_approvals_snapshot,
    enrich_discovery_resources_snapshot,
    enrich_requests_snapshot,
)
from zw_brain.domain.repositories.application import ApplicationRepository
from zw_brain.domain.repositories.approval import ApprovalRepository
from zw_brain.domain.repositories.resource_api import ResourceApiRepository
from zw_brain.shared import audit as audit_bus
from zw_brain.shared import db as db_module
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.migrate import ensure_runtime_schema
from zw_brain.shared.state_store import StateStore

TENANT = "sd-default"


@pytest.fixture()
def temp_db(monkeypatch: pytest.MonkeyPatch) -> Path:
    """空 schema、无参考数据注入 —— enrich 真空起点。"""
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "discovery_projection.db"
        monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
        monkeypatch.delenv("ZW_BRAIN_DATABASE_URL", raising=False)
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()
        ensure_runtime_schema()
        yield db_path
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()


@pytest.fixture()
def brain(temp_db: Path) -> BrainService:
    """完整 service（DatabaseStore.initialize 会注入 seed 参考数据）—— data.search 调用用。"""
    ds = DatabaseStore()
    ds.initialize()
    audit_bus.configure_sink(ds.append_audit_event)
    return BrainService(state_store=StateStore(database_store=ds))


def _seed_application(app_id: str, *, kind: str | None, resource_name: str, status: str = "submitted") -> None:
    ApplicationRepository().upsert_from_request(
        {
            "id": app_id,
            "status": status,
            "applicant": "张三",
            "applicantDept": "市数据局",
            "kind": kind,
            "resource_name": resource_name,
            "resourceId": f"res-{app_id}",
            "use_reason": "办理业务",
        },
        tenant_id=TENANT,
    )


def _seed_approval(app_id: str, status: str = "pending") -> None:
    ApplicationRepository().upsert_from_request(
        {"id": app_id, "status": status, "applicant": "李四", "applicantDept": "市数据局", "kind": "apply", "resource_name": "X"},
        tenant_id=TENANT,
    )
    ApprovalRepository().upsert_from_request_and_approval({"id": app_id, "status": status}, {}, tenant_id=TENANT)


def _seed_asset(
    code: str,
    *,
    title: str,
    status: str = "active",
    share_type: object = "1",
    resource_kind: object = None,
) -> None:
    asset: dict[str, object] = {
        "resource_code": code,
        "title": title,
        "lifecycle_status": status,
        "owner_org_id": "11370000MB284651XL",
        "owner_org_snapshot_json": {"org_name": "省大数据局"},
        "access_policy_json": {"share_type": share_type},
    }
    if resource_kind is not None:
        asset["resource_kind"] = resource_kind
    ResourceApiRepository().upsert_asset(asset, tenant_id=TENANT)


# ── requests ────────────────────────────────────────────────────────────────

def test_enrich_requests_replaces_seed_with_db_applications(temp_db: Path) -> None:
    _seed_application("APP-1", kind="apply", resource_name="人口库接口")
    _seed_application("APP-2", kind=None, resource_name="法人库接口")  # 旧 ungrouped 也算申请
    _seed_application("DEM-1", kind="require", resource_name="")  # 需求类——应被排除

    out = enrich_requests_snapshot({"requests": [{"id": "SEED-OLD", "resourceName": "seed"}]}, tenant_id=TENANT)
    ids = {r["id"] for r in out["requests"]}
    assert ids == {"APP-1", "APP-2"}, "应替换为申请类真实记录，排除需求类，丢弃 seed"
    card = next(r for r in out["requests"] if r["id"] == "APP-1")
    assert card["resourceName"] == "人口库接口"
    assert card["status"] == "submitted"
    assert card["applicant"] != "张三", "applicant 应经 mask_default 脱敏"


def test_enrich_requests_empty_when_db_empty(temp_db: Path) -> None:
    # C-1 单一事实源：空库 → 诚实空列表（不再回退 seed 演示单）。
    seed = {"requests": [{"id": "SEED-1", "resourceName": "seed 申请"}]}
    out = enrich_requests_snapshot(seed, tenant_id=TENANT)
    assert out["requests"] == [], "空库应给诚实空列表，不保留 seed 演示单"


def test_enrich_requests_excludes_demand_kinds(temp_db: Path) -> None:
    _seed_application("DEM-A", kind="require", resource_name="")
    _seed_application("DEM-B", kind="original_require", resource_name="")
    out = enrich_requests_snapshot({"requests": [{"id": "SEED"}]}, tenant_id=TENANT)
    assert out["requests"] == [], "全是需求类 → 无申请类 → 诚实空列表（不回退 seed）"


# ── approvals ─────────────────────────────────────────────────────────────────

def test_enrich_approvals_replaces_seed_with_db_cases(temp_db: Path) -> None:
    _seed_approval("APP-10", status="pending")
    _seed_approval("APP-11", status="under_review")
    out = enrich_approvals_snapshot({"approvals": [{"id": "SEED-OLD"}]}, tenant_id=TENANT)
    ids = {a["id"] for a in out["approvals"]}
    assert ids == {"APP-10", "APP-11"}
    assert all(a["suggestion"] == "待审" for a in out["approvals"])


def test_enrich_approvals_empty_when_db_empty(temp_db: Path) -> None:
    # C-1 单一事实源：空库 → 诚实空列表。
    seed = {"approvals": [{"id": "SEED-A", "suggestion": "x"}]}
    out = enrich_approvals_snapshot(seed, tenant_id=TENANT)
    assert out["approvals"] == []


# ── discovery.resources ───────────────────────────────────────────────────────

def test_enrich_discovery_resources_only_discoverable_statuses(temp_db: Path) -> None:
    # D53①（反转 D45.b，2026-06-06）：发现页只展示「已发布(active)」资源；
    # 待发布(approved_pending_publish)/草稿/审核/暂停/下线/过期均退出发现视图。
    _seed_asset("RES-1", title="停车场信息共享目录", status="active", share_type="1")
    _seed_asset("RES-2", title="已下线资源", status="revoked")  # 非已发布 → 排除
    _seed_asset("RES-3", title="待发布资源", status="approved_pending_publish", share_type="2")  # 待发布 → 退出发现
    _seed_asset("RES-4", title="草稿资源", status="draft")  # 非已发布 → 排除
    out = enrich_discovery_resources_snapshot(
        {"discovery": {"resources": [{"id": "seed-res", "name": "seed"}]}}, tenant_id=TENANT
    )
    cards = {c["id"]: c for c in out["discovery"]["resources"]}
    assert set(cards) == {"RES-1"}, "只展示已发布 active，待发布/revoked/draft 均排除"
    assert "RES-3" not in cards, "待发布资源必须退出发现视图（D53①）"
    assert cards["RES-1"]["name"] == "停车场信息共享目录"
    # status = 中文展示态（前端零词表，单一事实源 resource_lifecycle.lifecycle_label）；
    # lifecycleStatus = 机器原值，前端逻辑（申请门控/chip 抑制）只比对它。
    assert cards["RES-1"]["status"] == "已发布"  # active → 中文展示态（D53①，反转旧词「可复用」）
    assert cards["RES-1"]["lifecycleStatus"] == "active"
    assert cards["RES-1"]["provider"] == "省大数据局"
    # 共享类型（源表 DDL 权威：1=无条件 / 2=有条件）+ 色级
    assert cards["RES-1"]["shareType"] == "无条件共享"
    assert cards["RES-1"]["shareLevel"] == "open"


def test_enrich_discovery_resources_folds_legacy_kind(temp_db: Path) -> None:
    # Bug2（读路径折叠，D53）：存量库残留 legacy resource_kind='folder'/'url'/'link'/'service'
    # 的 active 行，发现卡 kind 必须折叠到 库表/文件/API，绝不把 folder/url 泄漏到「资源类型」筛选/徽标。
    _seed_asset("RK-FOLDER", title="文件夹资源", resource_kind="folder")
    _seed_asset("RK-URL", title="链接资源", resource_kind="url")
    _seed_asset("RK-SERVICE", title="融合服务资源", resource_kind="service")
    _seed_asset("RK-TABLE", title="库表资源", resource_kind="table")
    out = enrich_discovery_resources_snapshot(
        {"discovery": {"resources": [{"id": "seed-res", "name": "seed"}]}}, tenant_id=TENANT
    )
    cards = {c["id"]: c for c in out["discovery"]["resources"]}
    assert cards["RK-FOLDER"]["kind"] == "file", "folder → file（文件夹退役并入文件）"
    assert cards["RK-URL"]["kind"] == "file", "url → file（链接退役并入文件）"
    assert cards["RK-SERVICE"]["kind"] == "api", "service → api（历史别名）"
    assert cards["RK-TABLE"]["kind"] == "table"
    # 关键不变量：发现卡 kind 取值集合 ⊆ 收敛三态，绝无 folder/url 泄漏
    kinds = {c.get("kind") for c in out["discovery"]["resources"] if c.get("kind")}
    assert kinds <= {"table", "file", "api"}, f"发现卡资源类型必须收敛，泄漏：{kinds}"


def test_enrich_discovery_resources_empty_when_db_empty(temp_db: Path) -> None:
    # C-1 单一事实源：空库 → 诚实空发现列表。
    seed = {"discovery": {"resources": [{"id": "seed-res", "name": "seed"}]}}
    out = enrich_discovery_resources_snapshot(seed, tenant_id=TENANT)
    assert out["discovery"]["resources"] == []


# ── data.search 空 query（走 service + trust-stamp）─────────────────────────────

def test_data_search_empty_query_returns_real_resources(brain: BrainService) -> None:
    _seed_asset("RES-DS-1", title="空搜索应见的真实资源", status="active")
    result = invoke_trusted(brain, "data.search", {"query": ""}, role="ROLE_ORGAN_OPERATER")
    ids = {r["id"] for r in result["results"]}
    assert "RES-DS-1" in ids, "空搜索应返回 DB 全量真实资源（含新 seed 的 RES-DS-1）"


# ── requests.sharedType — 受理/审核两级（P21）路由信号 ──────────────────────

def test_request_card_shared_type_derives_from_resource_access_policy(temp_db: Path) -> None:
    """真实导入单 payload 不携带 shared_type → 读时按 resourceId 从资源 access_policy 派生。

    走查发现（wave1.5 真 UI 全栈实测）：此前卡片只投 payload.sharingType（恒缺）→
    有条件单在 P3ReviewDetail 永远被当无条件渲染、两级链路 UI 走不进。
    """
    _seed_asset("COND-RES", title="有条件资源", share_type="2")
    ApplicationRepository().upsert_from_request(
        {
            "id": "APP-COND",
            "status": "submitted",
            "applicant": "张三",
            "applicantDept": "市数据局",
            "kind": "apply",
            "resource_name": "有条件资源",
            "resourceId": "COND-RES",
        },
        tenant_id=TENANT,
    )
    out = enrich_requests_snapshot({"requests": []}, tenant_id=TENANT)
    card = next(r for r in out["requests"] if r["id"] == "APP-COND")
    assert card["sharedType"] == 2, "payload 缺位时应从资源 access_policy.share_type 派生"


def test_request_card_shared_type_payload_explicit_wins(temp_db: Path) -> None:
    """payload 显式 shared_type 优先于资源派生（在产单/运行时铸单可覆写）。"""
    _seed_asset("UNCOND-RES", title="无条件资源", share_type="1")
    ApplicationRepository().upsert_from_request(
        {
            "id": "APP-EXPLICIT",
            "status": "submitted",
            "applicant": "张三",
            "applicantDept": "市数据局",
            "kind": "apply",
            "resource_name": "无条件资源",
            "resourceId": "UNCOND-RES",
            "shared_type": 2,
        },
        tenant_id=TENANT,
    )
    out = enrich_requests_snapshot({"requests": []}, tenant_id=TENANT)
    card = next(r for r in out["requests"] if r["id"] == "APP-EXPLICIT")
    assert card["sharedType"] == 2, "payload 显式 shared_type 应优先于资源派生"


# ── S3 万级规模性能：deepcopy 开关 + assets 预取 非变异契约 ─────────────────────
# 默认 copy=True 保持纯函数语义（不变异传入快照，独立测试/独立调用方不破）；
# handler 链路传 copy=False 原地写（已在顶部统一深拷一次过）。

def test_enrich_requests_default_copy_does_not_mutate_input(temp_db: Path) -> None:
    """默认 copy=True：拿原 dict 调 enrich，断言原 dict 未被变异（非变异契约）。"""
    _seed_application("APP-NM", kind="apply", resource_name="人口库接口")
    original = {"requests": [{"id": "SEED-KEEP", "resourceName": "seed"}]}
    before = copy.deepcopy(original)
    out = enrich_requests_snapshot(original, tenant_id=TENANT)
    assert out is not original, "copy=True 应返回新 dict（不与入参同一对象）"
    assert original == before, "copy=True 不得变异传入快照"
    assert {r["id"] for r in out["requests"]} == {"APP-NM"}, "投影结果仍正确"


def test_enrich_requests_copy_false_writes_in_place(temp_db: Path) -> None:
    """copy=False：原地写同一 dict（identity 相同），且 requests 键被原地替换。"""
    _seed_application("APP-IP", kind="apply", resource_name="法人库接口")
    snap: dict = {"requests": [{"id": "SEED-OLD"}], "other": {"keep": 1}}
    out = enrich_requests_snapshot(snap, tenant_id=TENANT, copy=False)
    assert out is snap, "copy=False 应原地写、返回同一对象"
    assert {r["id"] for r in out["requests"]} == {"APP-IP"}
    assert out["other"] == {"keep": 1}, "原地写不应破坏其它键"


def test_enrich_approvals_default_copy_does_not_mutate_input(temp_db: Path) -> None:
    _seed_approval("APP-AP-NM", status="pending")
    original = {"approvals": [{"id": "SEED-A"}]}
    before = copy.deepcopy(original)
    out = enrich_approvals_snapshot(original, tenant_id=TENANT)
    assert out is not original
    assert original == before, "copy=True 不得变异传入快照"
    assert {a["id"] for a in out["approvals"]} == {"APP-AP-NM"}


def test_enrich_approvals_copy_false_writes_in_place(temp_db: Path) -> None:
    _seed_approval("APP-AP-IP", status="pending")
    snap: dict = {"approvals": [{"id": "SEED-A"}], "requests": []}
    out = enrich_approvals_snapshot(snap, tenant_id=TENANT, copy=False)
    assert out is snap
    assert {a["id"] for a in out["approvals"]} == {"APP-AP-IP"}


def test_enrich_discovery_default_copy_does_not_mutate_input(temp_db: Path) -> None:
    _seed_asset("RES-NM", title="可发现资源", status="active")
    original = {"discovery": {"resources": [{"id": "seed-res"}]}}
    before = copy.deepcopy(original)
    out = enrich_discovery_resources_snapshot(original, tenant_id=TENANT)
    assert out is not original
    assert original == before, "copy=True 不得变异传入快照"
    assert {c["id"] for c in out["discovery"]["resources"]} == {"RES-NM"}


def test_enrich_discovery_copy_false_writes_in_place(temp_db: Path) -> None:
    _seed_asset("RES-IP", title="可发现资源2", status="active")
    snap: dict = {"discovery": {"resources": [{"id": "seed-res"}]}}
    out = enrich_discovery_resources_snapshot(snap, tenant_id=TENANT, copy=False)
    assert out is snap
    assert {c["id"] for c in out["discovery"]["resources"]} == {"RES-IP"}


def test_enrich_discovery_uses_prefetched_assets_not_db(temp_db: Path) -> None:
    """assets 预取：传入的 asset 列表被直接使用，不回落 DB 自查（万级 4→1 收口的可测证据）。

    DB 里放一条与预取列表不同的资源；传入只含 fabricated 一行的 assets，断言投影只反映 assets，
    不掺 DB 行 → 证明 enrich 用的是预取列表（assets is not None 短路自查）。
    """
    _seed_asset("RES-IN-DB", title="DB 里的资源", status="active")
    fake_assets = ResourceApiRepository().list_assets(tenant_id=TENANT)
    # 预取列表里制造一行 DB 不会再扫到的视角：只取 RES-IN-DB，但若回落 DB 也会得同结果，
    # 故改用「空预取列表」证明确实没回落 DB。
    out = enrich_discovery_resources_snapshot(
        {"discovery": {"resources": [{"id": "seed"}]}}, tenant_id=TENANT, assets=[], copy=False
    )
    assert out["discovery"]["resources"] == [], "assets=[] 应被直接采用（空），不回落 DB 全扫"
    # 反向确认：assets=None 时回落 DB 自查能看到 RES-IN-DB（确保 [] 与 None 语义区分）。
    out2 = enrich_discovery_resources_snapshot(
        {"discovery": {"resources": []}}, tenant_id=TENANT, assets=None, copy=False
    )
    assert {c["id"] for c in out2["discovery"]["resources"]} == {"RES-IN-DB"}
    assert fake_assets, "sanity: DB 非空"
