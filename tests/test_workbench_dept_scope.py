"""部门数据隔离 M8 — 工作台部门管理员审核待办计数按本机构(+下级)可见域收口.

守护点（A4 slice）：
  - 部门管理员（ROLE_ORGAN_MANAGER）审核待办计数（待审核目录 / 待审核反向编目草稿 /
    待审核挂接资源 / 待审核服务）只数 owner_org 落在调用方可见域内的行：
      · visible_org_codes={orgA} → 只数 orgA 的 pending 行，不数 orgB；
      · visible_org_codes=set()（fail-closed）→ 计数全为 0；
      · visible_org_codes=None（全局）→ 数全量（既有行为，下界守卫）。
  - 平台队列（BUSIAUDIT _backlog_todos：待平台审核/发布/受理/汇总）刻意保持全局，
    不消费 visible_org_codes——同一组 seed 下，传 {orgA} / set() / None 的平台计数一致。

与 tests/test_workbench_backlog_projection.py 同 temp_db 模式 + 同 enrich 入参形态
（view dict + role + tenant_id；M8 多传 visible_org_codes 关键字）。owner_org 用机构**码**
作 owner_org_id 同时入 visible_org_codes，命中 org_in_scope 裸值快路径（无需 org_projection）。
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.domain.repositories.resource_api import ResourceApiRepository
from zw_brain.domain.workbench_backlog_projection import enrich_workbench_backlog
from zw_brain.shared import db as db_module
from zw_brain.shared.migrate import ensure_runtime_schema

TENANT = "sd-default"
ORG_A = "11370000MB284651XA"
ORG_B = "11370000MB284651XB"
MANAGER = "ROLE_ORGAN_MANAGER"
BUSIAUDIT = "ROLE_BUSIAUDIT"


@pytest.fixture()
def temp_db(monkeypatch: pytest.MonkeyPatch) -> Path:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "workbench_dept_scope.db"
        monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
        monkeypatch.delenv("ZW_BRAIN_DATABASE_URL", raising=False)
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()
        ensure_runtime_schema()
        yield db_path
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()


def _seed_two_org_review_backlog() -> None:
    """orgA / orgB 各自的部门审核态行 + 一组平台队列行（验平台保持全局）。

    管理员审核四类（每类 orgA 2 / orgB 1，便于断言「只数本机构」）：
      - 待审核目录 = catalog pending_review
      - 待审核反向编目草稿 = catalog draft ∧ source=reverse
      - 待审核挂接资源 = resource_asset(kind=table) pending_review
      - 待审核服务 = resource_asset(kind=api) pending_review
    平台队列（BUSIAUDIT，应保持全局）：approved_pending_publish 目录/资源 + pending_platform_review 目录。
    """
    catalog = CatalogRepository()
    resource = ResourceApiRepository()

    # ── 待审核目录（pending_review）：orgA×2 / orgB×1 ──
    for org, n in ((ORG_A, 2), (ORG_B, 1)):
        for i in range(n):
            catalog.upsert_from_resource(
                {"id": f"cat-rev-{org}-{i}", "name": f"待审核目录{org}{i}", "status": "pending_review", "provider": org},
                tenant_id=TENANT,
            )
    # ── 待审核反向编目草稿（draft ∧ source=reverse）：orgA×2 / orgB×1 ──
    for org, n in ((ORG_A, 2), (ORG_B, 1)):
        for i in range(n):
            catalog.upsert_from_resource(
                {"id": f"cat-reverse-{org}-{i}", "name": f"反向草稿{org}{i}", "status": "draft", "source": "reverse", "provider": org},
                tenant_id=TENANT,
            )
    # ── 待审核挂接资源（table pending_review）：orgA×2 / orgB×1 ──
    for org, n in ((ORG_A, 2), (ORG_B, 1)):
        for i in range(n):
            resource.upsert_asset(
                {"resource_code": f"res-rev-{org}-{i}", "title": f"挂接资源{org}{i}", "resource_kind": "table", "lifecycle_status": "pending_review", "owner_org_id": org},
                tenant_id=TENANT,
            )
    # ── 待审核服务（api pending_review）：orgA×2 / orgB×1 ──
    for org, n in ((ORG_A, 2), (ORG_B, 1)):
        for i in range(n):
            resource.upsert_asset(
                {"resource_code": f"api-rev-{org}-{i}", "title": f"服务{org}{i}", "resource_kind": "api", "lifecycle_status": "pending_review", "owner_org_id": org},
                tenant_id=TENANT,
            )

    # ── 平台队列（BUSIAUDIT 路径，应不受 visible_org_codes 影响）──
    # 待发布目录（approved_pending_publish）：orgA×1 / orgB×1 = 2
    for org in (ORG_A, ORG_B):
        catalog.upsert_from_resource(
            {"id": f"cat-pub-{org}", "name": f"待发布目录{org}", "status": "approved_pending_publish", "provider": org},
            tenant_id=TENANT,
        )
    # 待平台审核目录（pending_platform_review）：orgA×1 / orgB×1 = 2
    for org in (ORG_A, ORG_B):
        catalog.upsert_from_resource(
            {"id": f"cat-plat-{org}", "name": f"待平台审目录{org}", "status": "pending_platform_review", "provider": org},
            tenant_id=TENANT,
        )
    # 待发布资源（approved_pending_publish）：orgA×1 / orgB×1 = 2
    for org in (ORG_A, ORG_B):
        resource.upsert_asset(
            {"resource_code": f"res-pub-{org}", "title": f"待发布资源{org}", "lifecycle_status": "approved_pending_publish", "owner_org_id": org},
            tenant_id=TENANT,
        )


def _manager_todo_counts(visible_org_codes: set[str] | None) -> dict[str, str]:
    """跑 manager enrich，返回 {todo_id: title}（title 内含计数）。"""
    out = enrich_workbench_backlog(
        {"todos": []}, MANAGER, tenant_id=TENANT, visible_org_codes=visible_org_codes
    )
    return {t["id"]: t["title"] for t in out["todos"]}


def test_manager_review_counts_scoped_to_visible_orgA_only(temp_db: Path) -> None:
    """visible={orgA}：四类审核计数只反映 orgA（各 2 条），不含 orgB（各 1 条）。"""
    _seed_two_org_review_backlog()
    titles = _manager_todo_counts({ORG_A})
    # 各类 orgA = 2（若误数全量会是 3）。
    assert titles["backlog-catalog-dept-review"] == "待审核目录 2 条"
    assert titles["backlog-reverse-draft-review"] == "待审核反向编目草稿 2 条"
    assert titles["backlog-hookup-review"] == "待审核挂接资源 2 条"
    assert titles["backlog-api-review"] == "待审核服务 2 条"


def test_manager_review_counts_global_when_visible_none(temp_db: Path) -> None:
    """visible=None（全局/上帝视角）：四类审核计数为全量（orgA 2 + orgB 1 = 3），下界守卫。"""
    _seed_two_org_review_backlog()
    titles = _manager_todo_counts(None)
    assert titles["backlog-catalog-dept-review"] == "待审核目录 3 条"
    assert titles["backlog-reverse-draft-review"] == "待审核反向编目草稿 3 条"
    assert titles["backlog-hookup-review"] == "待审核挂接资源 3 条"
    assert titles["backlog-api-review"] == "待审核服务 3 条"


def test_manager_review_counts_fail_closed_empty_visible(temp_db: Path) -> None:
    """visible=set()（fail-closed）：四类审核计数全为 0 → 零积压不投待办（无空死链）。"""
    _seed_two_org_review_backlog()
    titles = _manager_todo_counts(set())
    assert "backlog-catalog-dept-review" not in titles
    assert "backlog-reverse-draft-review" not in titles
    assert "backlog-hookup-review" not in titles
    assert "backlog-api-review" not in titles


def test_busiaudit_platform_todos_unaffected_by_visible_org_codes(temp_db: Path) -> None:
    """平台队列（BUSIAUDIT _backlog_todos）保持全局：传 {orgA} / set() / None 平台计数一致。

    平台队列含跨 orgA/orgB 的行（待发布目录×2、待平台审核目录×2、待发布资源×2），
    visible_org_codes 只该收口 MANAGER 路径——BUSIAUDIT 路径无论传什么 scope 都数全量。
    """
    _seed_two_org_review_backlog()

    def platform_titles(visible: set[str] | None) -> dict[str, str]:
        out = enrich_workbench_backlog(
            {"todos": []}, BUSIAUDIT, tenant_id=TENANT, visible_org_codes=visible
        )
        return {t["id"]: t["title"] for t in out["todos"]}

    full = platform_titles(None)
    scoped = platform_titles({ORG_A})
    fail_closed = platform_titles(set())

    # 三态平台计数必须一致（不受 visible_org_codes 影响）。
    assert full == scoped == fail_closed
    # 且全为全量（跨 orgA+orgB 的 2 条），证明确实未被 {orgA} 误收口。
    assert full["backlog-catalog-publish"] == "待发布目录 2 条"
    assert full["backlog-catalog-platform-review"] == "待平台审核目录 2 条"
    assert full["backlog-resource-publish"] == "待发布资源 2 条"
