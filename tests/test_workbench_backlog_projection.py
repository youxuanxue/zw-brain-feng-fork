"""业务运营员工作台待办 — 真实库现算投影（缺陷 2 + E2 职责口径守卫）.

守护点：
  - ROLE_BUSIAUDIT 工作台 todos = 业务运营员真实职责（发布 / 受理 / 汇总），从真实库
    积压现算：待发布目录 + 待发布资源 + 待受理申请 + 待受理异议 + 待汇总需求。每条带深链。
  - 审核类（待审核目录/资源、待补全用途）属部门管理员职责，不再出现在业务运营员工作台
    （E2 纠正职责错配，0605 反馈 6.4#11 + D53）。
  - 待受理申请按 kind=apply 过滤——application_record 表混存申请/需求，需求另归「待汇总需求」。
  - 部门管理员（D55/P10）：在 sync_request_todos 已投部门审核待办上叠加供数侧目录审核待办
    （pending_review 深链 catalog-review），零积压不投。部门操作员 view 原样（enrich 不动）。
  - 零积压不生成待办（无空死链）；办理建议是分类型行动句（G4）。
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from zw_brain.domain.repositories.application import ApplicationRepository
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.domain.repositories.objection import ObjectionRepository
from zw_brain.domain.repositories.resource_api import ResourceApiRepository
from zw_brain.domain.repositories.supply_demand import SupplyDemandRepository
from zw_brain.domain.supply_demand_phase import PHASE_REGISTERED
from zw_brain.domain.workbench_backlog_projection import enrich_workbench_backlog
from zw_brain.shared import db as db_module
from zw_brain.shared.migrate import ensure_runtime_schema

TENANT = "sd-default"


@pytest.fixture()
def temp_db(monkeypatch: pytest.MonkeyPatch) -> Path:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "workbench_backlog.db"
        monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
        monkeypatch.delenv("ZW_BRAIN_DATABASE_URL", raising=False)
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()
        ensure_runtime_schema()
        yield db_path
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()


def _seed_application(app_repo: ApplicationRepository, code: str, status: str) -> None:
    app_repo.upsert_from_request(
        {
            "id": code,
            "kind": "apply",
            "status": status,
            "applicant": "op",
            "applicantDept": "部门A",
            "resourceName": f"申请单{code}",
        },
        tenant_id=TENANT,
    )


def _seed_backlog() -> None:
    catalog = CatalogRepository()
    catalog.upsert_from_resource(
        {"id": "cat-pub-1", "name": "待发布目录甲", "status": "approved_pending_publish", "provider": "11370000MB284651XL"},
        tenant_id=TENANT,
    )
    for i in (1, 2):
        catalog.upsert_from_resource(
            {"id": f"cat-rev-{i}", "name": f"待审核目录{i}", "status": "pending_review", "provider": "11370000MB284651XL"},
            tenant_id=TENANT,
        )

    resource = ResourceApiRepository()
    resource.upsert_asset(
        {"resource_code": "res-pub-1", "title": "待发布资源甲", "lifecycle_status": "approved_pending_publish", "owner_org_id": "11370000MB284651XL"},
        tenant_id=TENANT,
    )
    resource.upsert_asset(
        {"resource_code": "res-rev-1", "title": "待审核资源甲", "lifecycle_status": "pending_review", "owner_org_id": "11370000MB284651XL"},
        tenant_id=TENANT,
    )

    _seed_application(ApplicationRepository(), "app-sub-1", "submitted")

    SupplyDemandRepository().register_demand(
        demand_id="dmd-1",
        title="缺数据需求甲",
        applicant="op",
        applicant_dept="部门A",
        tenant_id=TENANT,
        phase=PHASE_REGISTERED,
    )

    ObjectionRepository().create_case(
        {"target_type": "resource", "target_id": "res-pub-1", "title": "异议甲", "status": "submitted"},
        tenant_id=TENANT,
    )


def test_busiaudit_workbench_todos_are_operator_duties(temp_db: Path) -> None:
    _seed_backlog()
    base = {"todos": [], "subtitle": "陈旧 seed 文案", "aiSummary": {"summary": "旧"}, "highlights": ["旧亮点"]}
    out = enrich_workbench_backlog(base, "ROLE_BUSIAUDIT", tenant_id=TENANT)
    todos = {t["id"]: t for t in out["todos"]}

    assert todos["backlog-catalog-publish"]["title"] == "待发布目录 1 条"
    assert todos["backlog-catalog-publish"]["href"].startswith("#/")
    assert todos["backlog-resource-publish"]["title"] == "待发布资源 1 条"
    assert todos["backlog-application"]["title"] == "待受理申请 1 条"
    assert todos["backlog-objection"]["title"] == "待受理异议 1 条"
    assert todos["backlog-demand"]["title"] == "待汇总需求 1 条"

    assert "backlog-catalog-review" not in todos
    assert "backlog-resource-review" not in todos
    assert "backlog-purpose-quality" not in todos

    assert "陈旧" not in out["subtitle"]
    assert out["highlights"] == []


def test_g4_action_summary_is_typed_action_sentence(temp_db: Path) -> None:
    _seed_backlog()
    out = enrich_workbench_backlog({"todos": []}, "ROLE_BUSIAUDIT", tenant_id=TENANT)
    summary = out["aiSummary"]["summary"]
    assert "条申请待受理" in summary
    assert "个目录待发布" in summary
    assert "请尽快处理" in summary
    assert "真实积压" not in summary


def test_demand_not_miscounted_as_application(temp_db: Path) -> None:
    """表混存申请/需求时，登记需求只进「待汇总需求」、不串进「待受理申请」。"""
    SupplyDemandRepository().register_demand(
        demand_id="dmd-only",
        title="只有需求无申请",
        applicant="op",
        applicant_dept="部门A",
        tenant_id=TENANT,
        phase=PHASE_REGISTERED,
    )
    out = enrich_workbench_backlog({"todos": []}, "ROLE_BUSIAUDIT", tenant_id=TENANT)
    todos = {t["id"]: t for t in out["todos"]}
    assert todos["backlog-demand"]["title"] == "待汇总需求 1 条"
    assert "backlog-application" not in todos


def test_busiaudit_empty_backlog_is_honest_empty(temp_db: Path) -> None:
    base = {"todos": [{"id": "stale", "title": "陈旧待办"}], "subtitle": "x", "aiSummary": {}, "highlights": []}
    out = enrich_workbench_backlog(base, "ROLE_BUSIAUDIT", tenant_id=TENANT)
    assert out["todos"] == []
    assert "没有待办积压" in out["subtitle"]
    assert "没有待办积压" in out["aiSummary"]["summary"]


def test_operater_view_untouched(temp_db: Path) -> None:
    """部门操作员（申请人）view 原样返回——待办由 sync_request_todos 真投影，enrich 不动。"""
    _seed_backlog()
    base = {"todos": [{"id": "REQ-x", "title": "申请进度跟踪", "href": "#/request-flow/request/REQ-x"}], "subtitle": "s"}
    out = enrich_workbench_backlog(base, "ROLE_ORGAN_OPERATER", tenant_id=TENANT)
    assert out is base


def test_manager_gets_provider_review_backlog_prepended(temp_db: Path) -> None:
    """D55/P10：部门管理员在既有待办上叠加供数侧目录审核待办（pending_review），深链 catalog-review。"""
    _seed_backlog()  # 2 条 pending_review catalog
    base = {
        "todos": [
            {"id": "REQ-x", "title": "资源申请待审核", "href": "#/request-flow/review/REQ-x"}
        ],
        "subtitle": "s",
    }
    out = enrich_workbench_backlog(base, "ROLE_ORGAN_MANAGER", tenant_id=TENANT)
    todos = {t["id"]: t for t in out["todos"]}
    # 供数审核待办前插，原有部门审核待办保留
    assert "backlog-catalog-dept-review" in todos
    assert todos["backlog-catalog-dept-review"]["title"] == "待审核目录 2 条"
    assert todos["backlog-catalog-dept-review"]["href"] == "#/provider/inbox/catalog-review"
    assert "REQ-x" in todos, "原有部门审核待办应保留"
    # 前插顺序：供数审核待办在原有待办之前
    assert out["todos"][0]["id"] == "backlog-catalog-dept-review"


def test_manager_zero_review_backlog_untouched(temp_db: Path) -> None:
    """D55/P10：无 pending_review 目录时部门管理员 view 原样返回（零积压不投，无空死链）。"""
    # 不 seed → 零 pending_review
    base = {"todos": [{"id": "REQ-y", "title": "x", "href": "#/request-flow/review/REQ-y"}], "subtitle": "s"}
    out = enrich_workbench_backlog(base, "ROLE_ORGAN_MANAGER", tenant_id=TENANT)
    assert out is base


def test_backlog_todos_count_matches_repo(temp_db: Path) -> None:
    _seed_backlog()
    out = enrich_workbench_backlog({"todos": []}, "ROLE_BUSIAUDIT", tenant_id=TENANT)
    todos = {t["id"]: t for t in out["todos"]}
    catalog = CatalogRepository()
    assert str(catalog.count_entries(tenant_id=TENANT, lifecycle_status="approved_pending_publish")) in todos["backlog-catalog-publish"]["title"]
    n_res_pub = len(ResourceApiRepository().list_assets(tenant_id=TENANT, lifecycle_status="approved_pending_publish"))
    assert str(n_res_pub) in todos["backlog-resource-publish"]["title"]
    n_obj = len(ObjectionRepository().list_cases(tenant_id=TENANT, status="submitted"))
    assert str(n_obj) in todos["backlog-objection"]["title"]
