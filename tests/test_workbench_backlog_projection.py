"""业务运营员工作台待办 — 真实库现算投影（缺陷 2 守卫）.

守护点：
  - ROLE_BUSIAUDIT 工作台 todos 从真实库积压现算（待发布/待审核目录 + 待审核资源 + 待受理申请），
    每条带深链到既有办理页；零积压不生成待办（无空死链）。
  - 其它角色 view 原样（待办由 sync_request_todos 真投影），enrich 不动它们。
  - 计数与真实库一致（投影 ≠ seed 写死文案）。
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from zw_brain.domain.repositories.application import ApplicationRepository
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.domain.repositories.resource_api import ResourceApiRepository
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


def _seed_backlog() -> None:
    catalog = CatalogRepository()
    # 待发布目录 ×1
    catalog.upsert_from_resource(
        {"id": "cat-pub-1", "name": "待发布目录甲", "status": "approved_pending_publish", "provider": "11370000MB284651XL"},
        tenant_id=TENANT,
    )
    # 待审核目录 ×2
    for i in (1, 2):
        catalog.upsert_from_resource(
            {"id": f"cat-rev-{i}", "name": f"待审核目录{i}", "status": "pending_review", "provider": "11370000MB284651XL"},
            tenant_id=TENANT,
        )
    # 待审核资源 ×1
    ResourceApiRepository().upsert_asset(
        {"resource_code": "res-rev-1", "title": "待审核资源甲", "lifecycle_status": "pending_review", "owner_org_id": "11370000MB284651XL"},
        tenant_id=TENANT,
    )


def test_busiaudit_workbench_todos_from_live_backlog(temp_db: Path) -> None:
    _seed_backlog()
    base = {"todos": [], "subtitle": "陈旧 seed 文案", "aiSummary": {"summary": "旧"}, "highlights": ["旧亮点"]}
    out = enrich_workbench_backlog(base, "ROLE_BUSIAUDIT", tenant_id=TENANT)
    todos = {t["id"]: t for t in out["todos"]}

    # 现算口径：有积压才出待办，计数=真实库该态行数，每条带深链。
    assert "backlog-catalog-publish" in todos
    assert "待发布目录 1 条" == todos["backlog-catalog-publish"]["title"]
    assert todos["backlog-catalog-publish"]["href"].startswith("#/")

    assert "backlog-catalog-review" in todos
    assert "待审核目录 2 条" == todos["backlog-catalog-review"]["title"]

    assert "backlog-resource-review" in todos
    assert "待审核资源 1 条" == todos["backlog-resource-review"]["title"]

    # 无待受理申请积压 → 不生成该条（无空死链）。
    assert "backlog-application" not in todos

    # 陈旧 seed subtitle/aiSummary/highlights 被现算结果替换。
    assert "陈旧" not in out["subtitle"]
    assert out["highlights"] == []


def test_busiaudit_empty_backlog_is_honest_empty(temp_db: Path) -> None:
    base = {"todos": [{"id": "stale", "title": "陈旧待办"}], "subtitle": "x", "aiSummary": {}, "highlights": []}
    out = enrich_workbench_backlog(base, "ROLE_BUSIAUDIT", tenant_id=TENANT)
    # 零积压 → 诚实空 todos（不回退陈旧 seed 待办）。
    assert out["todos"] == []
    assert "没有待办积压" in out["subtitle"]


def test_other_roles_view_untouched(temp_db: Path) -> None:
    _seed_backlog()
    base = {"todos": [{"id": "REQ-x", "title": "申请进度跟踪", "href": "#/request-flow/request/REQ-x"}], "subtitle": "s"}
    for role in ("ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"):
        out = enrich_workbench_backlog(base, role, tenant_id=TENANT)
        # 非业务运营员：原样返回（同一对象，不深拷贝、不重算）。
        assert out is base


def test_backlog_todos_count_matches_repo(temp_db: Path) -> None:
    _seed_backlog()
    out = enrich_workbench_backlog({"todos": []}, "ROLE_BUSIAUDIT", tenant_id=TENANT)
    todos = {t["id"]: t for t in out["todos"]}
    catalog = CatalogRepository()
    assert str(catalog.count_entries(tenant_id=TENANT, lifecycle_status="approved_pending_publish")) in todos["backlog-catalog-publish"]["title"]
    assert str(catalog.count_entries(tenant_id=TENANT, lifecycle_status="pending_review")) in todos["backlog-catalog-review"]["title"]
    n_res = len(ResourceApiRepository().list_assets(tenant_id=TENANT, lifecycle_status="pending_review"))
    assert str(n_res) in todos["backlog-resource-review"]["title"]
    # 申请积压为 0 时不出待办（与 repo 一致）。
    assert ApplicationRepository().count_by_statuses(statuses=["submitted", "under_review"], tenant_id=TENANT) == 0
    assert "backlog-application" not in todos
