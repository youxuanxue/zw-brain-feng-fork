"""J1 list snapshot projections — requests / approvals / discovery.resources 全量真实库投影。

D45 / 关 D43.c(1)。

enrich-direct 用例用 ``temp_db``（只建空 schema、**不**走 DatabaseStore.initialize 的参考
数据注入）→ DB 真空，自己 seed → 断言替换/排他/保留 seed 干净。data.search 用例需 service +
trust-stamp 调用，用 ``brain`` fixture（其 initialize 会注入参考资源）+ invoke_trusted。
**不依赖 .data/zw_brain.db**，CI 内可跑。
"""

from __future__ import annotations

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


def _seed_asset(code: str, *, title: str, status: str = "active", share_type: object = "1") -> None:
    ResourceApiRepository().upsert_asset(
        {
            "resource_code": code,
            "title": title,
            "lifecycle_status": status,
            "owner_org_id": "11370000MB284651XL",
            "owner_org_snapshot_json": {"org_name": "省大数据局"},
            "access_policy_json": {"share_type": share_type},
        },
        tenant_id=TENANT,
    )


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
    # D45.b：发现页默认只展示「可用」资源 = active + 待发布；草稿/审核/暂停/下线/过期排除。
    _seed_asset("RES-1", title="停车场信息共享目录", status="active", share_type="1")
    _seed_asset("RES-2", title="已下线资源", status="revoked")  # 非可用 → 排除
    _seed_asset("RES-3", title="待发布资源", status="approved_pending_publish", share_type="2")
    _seed_asset("RES-4", title="草稿资源", status="draft")  # 非可用 → 排除
    out = enrich_discovery_resources_snapshot(
        {"discovery": {"resources": [{"id": "seed-res", "name": "seed"}]}}, tenant_id=TENANT
    )
    cards = {c["id"]: c for c in out["discovery"]["resources"]}
    assert set(cards) == {"RES-1", "RES-3"}, "只展示 active + 待发布，排除 revoked / draft"
    assert cards["RES-1"]["name"] == "停车场信息共享目录"
    assert cards["RES-1"]["status"] == "可复用"  # active → 中文展示态
    assert cards["RES-3"]["status"] == "待发布"  # approved_pending_publish
    assert cards["RES-1"]["provider"] == "省大数据局"
    # 共享类型（源表 DDL 权威：1=无条件 / 2=有条件）+ 色级
    assert cards["RES-1"]["shareType"] == "无条件共享"
    assert cards["RES-1"]["shareLevel"] == "open"
    assert cards["RES-3"]["shareType"] == "有条件共享"
    assert cards["RES-3"]["shareLevel"] == "conditional"


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
