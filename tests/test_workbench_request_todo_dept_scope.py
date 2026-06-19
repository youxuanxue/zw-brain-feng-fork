"""部门数据隔离「第七面」—— 工作台申请待办（sync_request_todos 平行路径）读时按机构/个人收口.

#294/#296 把快照 requests/approvals/delivery 面按机构收口，但工作台待办还有一条平行投影
路径 ``sync_request_todos``——#295 的行内办理（申请受理/审核）正建在其上，#294 从没碰过它。
本测试守护该路径的读时收口：
  - 部门管理员申请审核/汇总待办（category review/summary，办别人的单）→ 本机构可见域
    （D61 裁决②；None=全量放行 / 空集=fail-closed 全丢 / 集=只留域内）；
  - 部门操作员申请进度/补录待办（category apply-progress/supplement-*，我的单）→ 个人
    （D61 裁决③；payload.applicant==caller_actor；无身份上下文 → fail-closed 空）；
  - 业务运营员受理待办（category accept）保持全局（D61 裁决④），不受 visible_org_codes 影响。

与 test_workbench_dept_scope.py 同 temp_db + 同 enrich 直调形态。申请待办须有真实
application_record 背书（todo id == payload['id'] == request_id），enrich 据库现算可见 id 集。
owner 用机构**码**作 applicantDept，命中 org_in_scope 裸值快路径（无需 org_projection）。
"""

from __future__ import annotations

import pytest

from zw_brain.domain.repositories.application import ApplicationRepository
from zw_brain.domain.workbench_backlog_projection import enrich_workbench_backlog
from zw_brain.shared.migrate import ensure_runtime_schema

TENANT = "sd-default"
ORG_A = "11370000MB284651XA"
ORG_B = "11370000MB284651XB"
MANAGER = "ROLE_ORGAN_MANAGER"
OPERATER = "ROLE_ORGAN_OPERATER"
BUSIAUDIT = "ROLE_BUSIAUDIT"


@pytest.fixture()
def temp_db() -> None:
    # Per-test isolation is provided by the conftest autouse fixture (a fresh
    # empty PG clone via ZW_BRAIN_DATABASE_URL); just ensure the schema is built.
    ensure_runtime_schema()


def _seed_app(code: str, *, org: str, applicant: str, status: str) -> None:
    ApplicationRepository().upsert_from_request(
        {
            "id": code,
            "kind": "apply",
            "status": status,
            "applicant": applicant,
            "applicantDept": org,
            "resourceName": f"申请{code}",
        },
        tenant_id=TENANT,
    )


def _todo(code: str, category: str) -> dict:
    return {"id": code, "title": f"{code} 待办", "href": f"#/request-flow/review/{code}", "category": category}


def _ids(out: dict) -> list[str]:
    return [str(t.get("id")) for t in out.get("todos", [])]


# ── 部门管理员：申请审核/汇总待办按本机构可见域收口（D61 裁决②）───────────────────────
def _manager_view() -> dict:
    return {
        "todos": [
            _todo("APP-A", "review"),
            _todo("APP-B", "review"),
            _todo("APP-A", "summary"),  # 同单汇总待办（id 同 APP-A，category 区分）
        ]
    }


def _seed_two_org_apps() -> None:
    _seed_app("APP-A", org=ORG_A, applicant="mgr-a", status="dept_approved")
    _seed_app("APP-B", org=ORG_B, applicant="mgr-b", status="dept_approved")


def test_manager_review_todos_scoped_to_visible_org(temp_db: None) -> None:
    _seed_two_org_apps()
    out = enrich_workbench_backlog(_manager_view(), MANAGER, tenant_id=TENANT, visible_org_codes={ORG_A})
    ids = _ids(out)
    assert "APP-A" in ids, "本机构申请审核待办保留"
    assert "APP-B" not in ids, "别部门申请审核待办剔除（消除可见+点了403反模式）"


def test_manager_review_todos_fail_closed_on_empty_visible(temp_db: None) -> None:
    _seed_two_org_apps()
    out = enrich_workbench_backlog(_manager_view(), MANAGER, tenant_id=TENANT, visible_org_codes=set())
    assert _ids(out) == [], "空集 fail-closed：申请审核/汇总待办全丢"


def test_manager_review_todos_global_when_visible_none(temp_db: None) -> None:
    _seed_two_org_apps()
    out = enrich_workbench_backlog(_manager_view(), MANAGER, tenant_id=TENANT, visible_org_codes=None)
    ids = _ids(out)
    assert {"APP-A", "APP-B"} <= set(ids), "全局视角（None）保留全量，不收口"


def test_manager_unbacked_review_todo_dropped(temp_db: None) -> None:
    # 无 application_record 背书的申请审核待办（id 不在任何可见集）→ 被剔除（fail-closed）。
    _seed_two_org_apps()
    view = {"todos": [_todo("APP-GHOST", "review")]}
    out = enrich_workbench_backlog(view, MANAGER, tenant_id=TENANT, visible_org_codes={ORG_A})
    assert "APP-GHOST" not in _ids(out)


# ── 部门操作员：申请进度/补录待办按本机构可见域收口（D61 裁决②，同 MANAGER + 快照 requests 面）─
# 注：裁决③「我的申请按个人」由 requests 面 mine 标记承载（与 #294 一致）——当前 actor 是 role 级
# 身份（user:gov:<role>:*），按个人 drop 在跨部门操作员间无隔离效果，dept-scope 才真隔离。
def _operator_view() -> dict:
    return {
        "todos": [
            _todo("APP-MINE", "apply-progress"),
            _todo("APP-OTHER", "apply-progress"),
            _todo("APP-MINE", "supplement-township"),
        ]
    }


def _seed_two_org_progress_apps() -> None:
    _seed_app("APP-MINE", org=ORG_A, applicant="alice", status="pending")
    _seed_app("APP-OTHER", org=ORG_B, applicant="bob", status="pending")


def test_operator_progress_todos_scoped_to_visible_org(temp_db: None) -> None:
    _seed_two_org_progress_apps()
    out = enrich_workbench_backlog(_operator_view(), OPERATER, tenant_id=TENANT, visible_org_codes={ORG_A})
    ids = _ids(out)
    assert "APP-MINE" in ids, "本机构申请进度/补录待办保留"
    assert "APP-OTHER" not in ids, "别部门申请进度待办不可见（部门收口，D61②）"


def test_operator_progress_todos_fail_closed_on_empty_visible(temp_db: None) -> None:
    _seed_two_org_progress_apps()
    out = enrich_workbench_backlog(_operator_view(), OPERATER, tenant_id=TENANT, visible_org_codes=set())
    assert _ids(out) == [], "空集 fail-closed：申请进度/补录待办全丢"


def test_operator_progress_todos_global_when_visible_none(temp_db: None) -> None:
    _seed_two_org_progress_apps()
    out = enrich_workbench_backlog(_operator_view(), OPERATER, tenant_id=TENANT, visible_org_codes=None)
    assert {"APP-MINE", "APP-OTHER"} <= set(_ids(out)), "全局视角（None）保留全量，不收口"


# ── 业务运营员：受理待办（accept）保持全局，不受 visible_org_codes 影响（D61 裁决④）──────
def test_busiaudit_accept_todo_stays_global(temp_db: None) -> None:
    _seed_app("APP-SUB", org=ORG_B, applicant="op-b", status="submitted")
    view = {"todos": [_todo("APP-SUB", "accept")]}
    # 传一个**与 APP-SUB 机构无关**的 visible 集，受理待办仍须保留（业务运营员全局受理）。
    out = enrich_workbench_backlog(view, BUSIAUDIT, tenant_id=TENANT, visible_org_codes={ORG_A})
    assert "APP-SUB" in _ids(out), "业务运营员受理待办全局，不被部门收口剔除"
