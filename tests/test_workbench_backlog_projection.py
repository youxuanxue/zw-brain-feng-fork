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

from typing import Any

import pytest

from zw_brain.domain.repositories.application import ApplicationRepository
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.domain.repositories.objection import ObjectionRepository
from zw_brain.domain.repositories.resource_api import ResourceApiRepository
from zw_brain.domain.repositories.supply_demand import SupplyDemandRepository
from zw_brain.domain.supply_demand_phase import PHASE_REGISTERED
from zw_brain.domain.workbench_backlog_projection import _backlog_todos, enrich_workbench_backlog
from zw_brain.shared.migrate import ensure_runtime_schema

TENANT = "sd-default"


@pytest.fixture()
def temp_db() -> None:
    # Per-test isolation is provided by the conftest autouse fixture (a fresh
    # empty PG clone via ZW_BRAIN_DATABASE_URL); just ensure the schema is built.
    ensure_runtime_schema()


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
    # D57⑧ 两级各自入账：反向编目草稿（部门审，MANAGER）+ 平台审档目录（BUSIAUDIT）。
    catalog.upsert_from_resource(
        {"id": "cat-reverse-draft-1", "name": "反向编目草稿甲", "status": "draft", "source": "reverse", "provider": "11370000MB284651XL"},
        tenant_id=TENANT,
    )
    catalog.upsert_from_resource(
        {"id": "cat-platform-1", "name": "待平台审目录甲", "status": "pending_platform_review", "provider": "11370000MB284651XL"},
        tenant_id=TENANT,
    )

    resource = ResourceApiRepository()
    resource.upsert_asset(
        {"resource_code": "res-pub-1", "title": "待发布资源甲", "lifecycle_status": "approved_pending_publish", "owner_org_id": "11370000MB284651XL"},
        tenant_id=TENANT,
    )
    # 挂接审核口径：库表 / 文件资产 pending_review（G4，深链 hookup-review）。
    resource.upsert_asset(
        {"resource_code": "res-rev-1", "title": "待审核挂接资源甲", "resource_kind": "table", "lifecycle_status": "pending_review", "owner_org_id": "11370000MB284651XL"},
        tenant_id=TENANT,
    )
    # 服务注册审核口径：API 资产 pending_review（G4，深链 API 服务向导行内审核）。
    resource.upsert_asset(
        {"resource_code": "api-rev-1", "title": "待审核服务甲", "resource_kind": "api", "lifecycle_status": "pending_review", "owner_org_id": "11370000MB284651XL"},
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


# 模拟 sync_request_todos 已投进 view 的「逐单受理待办」（携行内决策 action）。
# enrich_workbench_backlog 现增量保留它们、不再整体替换（workbench inline action）。
def _accept_todo(request_id: str, *, conditional: bool = False) -> dict[str, Any]:
    cap = "application.platform_approve" if conditional else "approval.case.decide"
    return {
        "id": request_id,
        "title": f"{request_id}资源申请待受理",
        "status": "待受理",
        "href": f"#/request-flow/review/{request_id}",
        "category": "accept",
        "action": {"kind": "decision", "capability": cap, "gate": cap, "basePayload": {"request_id": request_id}, "context": [], "decisions": []},
    }


def test_busiaudit_workbench_todos_are_operator_duties(temp_db: None) -> None:
    _seed_backlog()
    # sync 已投的逐单受理待办（携 action）在 view 里——enrich 增量保留，不整体替换。
    base = {
        "todos": [_accept_todo("app-sub-1")],
        "subtitle": "陈旧 seed 文案",
        "aiSummary": {"summary": "旧"},
        "highlights": ["旧亮点"],
    }
    out = enrich_workbench_backlog(base, "ROLE_BUSIAUDIT", tenant_id=TENANT)
    todos = {t["id"]: t for t in out["todos"]}

    assert todos["backlog-catalog-publish"]["title"] == "待发布目录 1 条"
    assert todos["backlog-catalog-publish"]["href"].startswith("#/")
    assert todos["backlog-resource-publish"]["title"] == "待发布资源 1 条"
    # 逐单受理待办（携行内决策 action）被增量保留，不被聚合替换掉。
    assert todos["app-sub-1"]["category"] == "accept"
    assert todos["app-sub-1"]["action"]["kind"] == "decision"
    # 聚合「待受理申请」候选被剔除——逐单受理待办已逐条覆盖，避免双算。
    assert "backlog-application" not in todos
    assert todos["backlog-objection"]["title"] == "待受理异议 1 条"
    assert todos["backlog-demand"]["title"] == "待汇总需求 1 条"
    # D57⑧：平台审待办归业务运营员（正向部门审通过 + 反向部门审通过共用平台档），
    # 深链目录审核收件箱（BUSIAUDIT 档=平台审）。
    assert todos["backlog-catalog-platform-review"]["title"] == "待平台审核目录 1 条"
    assert todos["backlog-catalog-platform-review"]["href"] == "#/provider/inbox/catalog-review"

    assert "backlog-catalog-review" not in todos
    assert "backlog-resource-review" not in todos
    assert "backlog-purpose-quality" not in todos
    # 部门审类（含反向编目部门审）不入业务运营员工作台（D57⑧ 部门审归 MANAGER）。
    assert "backlog-reverse-draft-review" not in todos

    assert "陈旧" not in out["subtitle"]
    assert out["highlights"] == []


def test_g4_action_summary_is_typed_action_sentence(temp_db: None) -> None:
    _seed_backlog()
    # 含一条逐单受理待办 → 办理建议应拼出「N 条申请待受理」分句。
    out = enrich_workbench_backlog({"todos": [_accept_todo("app-sub-1")]}, "ROLE_BUSIAUDIT", tenant_id=TENANT)
    summary = out["aiSummary"]["summary"]
    assert "条申请待受理" in summary
    assert "个目录待发布" in summary
    assert "请尽快处理" in summary
    assert "真实积压" not in summary


def test_demand_not_miscounted_as_application(temp_db: None) -> None:
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


def test_busiaudit_empty_backlog_is_honest_empty(temp_db: None) -> None:
    # 无 sync 受理待办（todos 空）+ 空库 → 增量后仍为空，诚实空态。
    base: dict[str, Any] = {"todos": [], "subtitle": "x", "aiSummary": {}, "highlights": []}
    out = enrich_workbench_backlog(base, "ROLE_BUSIAUDIT", tenant_id=TENANT)
    assert out["todos"] == []
    assert "没有待办积压" in out["subtitle"]
    assert "没有待办积压" in out["aiSummary"]["summary"]


def test_busiaudit_augments_keeps_accept_todos_no_application_double(temp_db: None) -> None:
    """BUSIAUDIT enrich 改增量：逐单受理待办（携 action）存活、聚合「待受理申请」不重复双算，
    其余聚合候选（发布/异议/督办/需求/平台审）作深链待办保留。"""
    _seed_backlog()  # 1 条 submitted 申请 → 聚合「待受理申请」count=1
    # sync 已逐单投 2 条受理待办（携行内决策 action）。
    base: dict[str, Any] = {
        "todos": [_accept_todo("app-sub-1", conditional=True), _accept_todo("app-sub-2")],
        "subtitle": "陈旧",
    }
    out = enrich_workbench_backlog(base, "ROLE_BUSIAUDIT", tenant_id=TENANT)
    todos = {t["id"]: t for t in out["todos"]}
    # 逐单受理待办存活且仍携 action（行内可办理的唯一载体）。
    assert todos["app-sub-1"]["action"]["capability"] == "application.platform_approve"
    assert todos["app-sub-2"]["action"]["capability"] == "approval.case.decide"
    # 聚合「待受理申请」候选被剔除——避免与逐单受理待办双算。
    assert "backlog-application" not in todos
    # 其余聚合候选保留（category=backlog）。异议受理经 M5 re-grain 为行内 decision-list（经 BUSIAUDIT
    # 增量 enrich 存活）；督办/需求汇总未 re-grain（多步）仍为深链、不带 action。G4 行动分句叫 actionClause。
    assert todos["backlog-objection"]["category"] == "backlog"
    assert todos["backlog-demand"]["category"] == "backlog"
    assert todos["backlog-objection"]["action"]["kind"] == "decision-list"
    assert todos["backlog-objection"]["action"]["items"][0]["capability"] == "objection.case.accept"
    assert "action" not in todos["backlog-demand"]
    assert isinstance(todos["backlog-demand"]["actionClause"], str)


def test_operater_keeps_progress_todos_with_honest_advice(temp_db: None) -> None:
    """部门操作员（D57②/R-8）：申请进度待办内容不被改写；subtitle/办理建议改为真实进度
    现算（不再漏出 seed 虚构「停车场…黄金旅程」叙事）。

    「第七面」收口：apply-progress/supplement 待办按本机构可见域收口；本测试不传
    visible_org_codes（默认 None=全局视角），两条待办均有真实在产单背书（id=request_id）故全部
    保留——验「内容不改写」与「办理建议现算」（dept-scope 行级守卫见 test_workbench_request_todo_dept_scope）。
    """
    _seed_backlog()
    # 在产单背书两条待办（id 即 request_id，与 sync_request_todos 口径一致；生产中待办恒有库背书）。
    app_repo = ApplicationRepository()
    _seed_application(app_repo, "REQ-x", "pending")
    _seed_application(app_repo, "REQ-x-sup", "supplementing")
    base = {
        "todos": [
            {"id": "REQ-x", "title": "申请进度跟踪", "href": "#/request-flow/request/REQ-x", "category": "apply-progress"},
            {"id": "REQ-x-sup", "title": "差异补录任务", "href": "#/request-flow/request/REQ-x-sup", "category": "supplement-township"},
        ],
        "subtitle": "停车场信息复用申请待看进度（seed 虚构）",
        "aiSummary": {"summary": "黄金旅程（seed 虚构）"},
    }
    out = enrich_workbench_backlog(base, "ROLE_ORGAN_OPERATER", tenant_id=TENANT)
    assert [t["id"] for t in out["todos"]] == ["REQ-x", "REQ-x-sup"], "全局视角下申请待办保留、内容不改写"
    assert "停车场" not in out["subtitle"] and "虚构" not in out["subtitle"]
    assert "1 条申请在办" in out["aiSummary"]["summary"]
    assert "1 项补录任务待完成" in out["aiSummary"]["summary"]


def test_operater_empty_progress_is_honest_empty(temp_db: None) -> None:
    base = {"todos": [], "subtitle": "seed 旧文案", "aiSummary": {"summary": "旧"}}
    out = enrich_workbench_backlog(base, "ROLE_ORGAN_OPERATER", tenant_id=TENANT)
    assert out["todos"] == []
    assert "没有进行中的申请" in out["subtitle"]
    assert "没有进行中的申请" in out["aiSummary"]["summary"]


def test_security_audit_is_readonly_supervisor_view(temp_db: None) -> None:
    """安全审计员（D57②/R-8）：纯只读监督岗——todos 恒空（不投写待办、不造仪表盘），
    办理建议为指向查审计的诚实指引（清除 seed 虚构「绕开模板重复采集告警」叙事）。"""
    _seed_backlog()
    base = {"todos": [{"id": "stale", "title": "旧告警"}], "subtitle": "绕开模板重复采集（seed 虚构）", "aiSummary": {"summary": "旧"}}
    out = enrich_workbench_backlog(base, "ROLE_SECURITY_AUDIT", tenant_id=TENANT)
    assert out["todos"] == []
    assert "只读监督" in out["subtitle"]
    assert "查审计" in out["aiSummary"]["summary"]
    assert "绕开模板" not in out["subtitle"]


def test_system_ops_view_is_honest(temp_db: None) -> None:
    """平台运维员（D57②/R-8）：运维核查语境，零积压给诚实空态。"""
    out = enrich_workbench_backlog({"todos": [], "subtitle": "x", "aiSummary": {}}, "ROLE_SYSTEM", tenant_id=TENANT)
    assert out["todos"] == []
    assert "没有运维待办积压" in out["subtitle"]
    assert "服务调用监控" in str(out["aiSummary"]["basis"])


def test_manager_gets_provider_review_backlog_prepended(temp_db: None) -> None:
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
    # D57⑧：反向编目部门审待办归部门管理员，深链反向编目审核收件箱（与收件箱口径
    # source=reverse ∧ draft 同源）；平台审待办不入管理员工作台。
    assert todos["backlog-reverse-draft-review"]["title"] == "待审核反向编目草稿 1 条"
    assert todos["backlog-reverse-draft-review"]["href"] == "#/provider/inbox/field-decision"
    assert "backlog-catalog-platform-review" not in todos
    assert "REQ-x" in todos, "原有部门审核待办应保留"
    # 前插顺序：供数审核待办在原有待办之前
    assert out["todos"][0]["id"] == "backlog-catalog-dept-review"


def test_manager_zero_review_backlog_keeps_todos_rewrites_advice(temp_db: None) -> None:
    """D55/P10 + D57②/R-8：无 pending_review 时不投供数审核待办（零积压无空死链），
    既有待办保留；subtitle/办理建议仍重写为真实现算（不再漏出 seed 虚构叙事）。"""
    # 不 seed → 零 pending_review
    base = {"todos": [{"id": "REQ-y", "title": "资源申请待审核", "href": "#/request-flow/review/REQ-y"}], "subtitle": "涉企采集准入待判定（seed 虚构）"}
    out = enrich_workbench_backlog(base, "ROLE_ORGAN_MANAGER", tenant_id=TENANT)
    assert [t["id"] for t in out["todos"]] == ["REQ-y"]
    assert "涉企采集" not in out["subtitle"]
    assert "1 条申请审批/汇总待办" in out["aiSummary"]["summary"]


def test_backlog_todos_count_matches_repo(temp_db: None) -> None:
    _seed_backlog()
    out = enrich_workbench_backlog({"todos": []}, "ROLE_BUSIAUDIT", tenant_id=TENANT)
    todos = {t["id"]: t for t in out["todos"]}
    catalog = CatalogRepository()
    assert str(catalog.count_entries(tenant_id=TENANT, lifecycle_status="approved_pending_publish")) in todos["backlog-catalog-publish"]["title"]
    n_res_pub = len(ResourceApiRepository().list_assets(tenant_id=TENANT, lifecycle_status="approved_pending_publish"))
    assert str(n_res_pub) in todos["backlog-resource-publish"]["title"]
    n_obj = len(ObjectionRepository().list_cases(tenant_id=TENANT, status="submitted"))
    assert str(n_obj) in todos["backlog-objection"]["title"]


# ── M5 行内决策（decision-list 载荷）守卫 ─────────────────────────────────────
# 每条 re-grain 待办 = count 头条（title/href/actionClause 不变）+ action.kind=="decision-list"，
# items 逐条枚举真实实体（非计数），每项带正确 capability/gate/basePayload/decisions。
# 不 re-grain 的三类（督办/需求/服务审核）保 count + href、**无** action。零积压不投。

_SEED_OWNER = "11370000MB284651XL"


def _decision_labels(item: dict) -> list[str]:
    return [d["label"] for d in item["decisions"]]


def test_busiaudit_publish_todos_carry_decision_list_action(temp_db: None) -> None:
    """待发布目录 / 待发布资源 re-grain 为 decision-list：逐实体 + 发布单决策。"""
    _seed_backlog()
    out = enrich_workbench_backlog({"todos": []}, "ROLE_BUSIAUDIT", tenant_id=TENANT)
    todos = {t["id"]: t for t in out["todos"]}

    cat = todos["backlog-catalog-publish"]
    assert cat["title"] == "待发布目录 1 条"  # count 头条不变
    assert cat["href"].startswith("#/")  # href 兜底保留
    assert cat["action"]["kind"] == "decision-list"
    items = cat["action"]["items"]
    assert [i["id"] for i in items] == ["cat-pub-1"]  # 枚举真实体而非计数
    assert items[0]["capability"] == "catalog.entry.publish"
    assert items[0]["gate"] == "catalog.entry.publish"
    assert items[0]["basePayload"] == {"catalog_code": "cat-pub-1"}
    assert _decision_labels(items[0]) == ["发布"]
    assert items[0]["label"] == "待发布目录甲"
    assert items[0]["context"] == [{"label": "目录", "value": "待发布目录甲"}]

    res = todos["backlog-resource-publish"]
    res_item = res["action"]["items"][0]
    assert res_item["capability"] == "resource.asset.publish"
    assert res_item["basePayload"] == {"resource_code": "res-pub-1"}
    assert _decision_labels(res_item) == ["发布"]


def test_busiaudit_platform_review_todo_carries_approve_reject(temp_db: None) -> None:
    """待平台审核目录 re-grain：通过(approve)/驳回(reject+reason) 双决策，capability=catalog.entry.review。"""
    _seed_backlog()
    out = enrich_workbench_backlog({"todos": []}, "ROLE_BUSIAUDIT", tenant_id=TENANT)
    todos = {t["id"]: t for t in out["todos"]}
    action = todos["backlog-catalog-platform-review"]["action"]
    assert action["kind"] == "decision-list"
    item = action["items"][0]
    assert item["id"] == "cat-platform-1"
    assert item["capability"] == "catalog.entry.review"
    assert item["basePayload"] == {"catalog_code": "cat-platform-1"}
    approve, reject = item["decisions"]
    assert approve["payload"] == {"decision": "approve"} and approve["tone"] == "primary"
    assert reject["payload"] == {"decision": "reject"} and reject["tone"] == "danger"
    assert reject["needsReason"] is True and reject["reasonKey"] == "reason"


def test_busiaudit_objection_todo_carries_accept_decision(temp_db: None) -> None:
    """待受理异议 re-grain：受理单决策，capability=objection.case.accept，basePayload.objection_id。"""
    _seed_backlog()
    out = enrich_workbench_backlog({"todos": []}, "ROLE_BUSIAUDIT", tenant_id=TENANT)
    todos = {t["id"]: t for t in out["todos"]}
    item = todos["backlog-objection"]["action"]["items"][0]
    assert item["capability"] == "objection.case.accept"
    assert set(item["basePayload"]) == {"objection_id"}
    assert item["basePayload"]["objection_id"]  # 真实 case id（uuid）
    assert _decision_labels(item) == ["受理"]
    # context 用 case 暴露字段（责任单位/事项），缺失跳过——此处 provider/target 均有值。
    ctx_labels = [r["label"] for r in item["context"]]
    assert "责任单位" in ctx_labels


def test_busiaudit_non_regrained_todos_have_no_action(temp_db: None) -> None:
    """督办/需求汇总不 re-grain：保 count + href，**无** action（多步，留兜底深链）。"""
    _seed_backlog()
    # 事件式督办：在非终态 case 上加 escalate 过程事件即进督办队列（不改 case.status）。
    obj = ObjectionRepository()
    case = obj.list_cases(tenant_id=TENANT, status="submitted")[0]
    obj.add_process(case.id, node_name="升级督办", action_type="escalate", action_result="pass")
    out = enrich_workbench_backlog({"todos": []}, "ROLE_BUSIAUDIT", tenant_id=TENANT)
    todos = {t["id"]: t for t in out["todos"]}
    assert "action" not in todos["backlog-objection-supervised"]
    assert todos["backlog-objection-supervised"]["href"]
    assert "action" not in todos["backlog-demand"]
    assert todos["backlog-demand"]["href"]


def test_application_aggregate_not_regrained(temp_db: None) -> None:
    """待受理申请不 re-grain（受理面跨多角色 + 申请单一事实源在 sync）：原始聚合保 count + href、无 action。
    注：BUSIAUDIT enrich 会进一步**剔除**该聚合项（逐单受理待办已覆盖，见
    test_busiaudit_augments_keeps_accept_todos_no_application_double），故在 _backlog_todos 原始层断言。"""
    _seed_backlog()
    todos = {t["id"]: t for t in _backlog_todos(TENANT)}
    assert "action" not in todos["backlog-application"]
    assert todos["backlog-application"]["href"]


def test_zero_count_regrained_types_emit_nothing(temp_db: None) -> None:
    """零积压不投待办（含 re-grain 类型）——空库下 BUSIAUDIT todos 全空，无空死链/空 decision-list。"""
    out = enrich_workbench_backlog({"todos": []}, "ROLE_BUSIAUDIT", tenant_id=TENANT)
    assert out["todos"] == []


def test_manager_review_todos_carry_decision_list_with_right_caps(temp_db: None) -> None:
    """MANAGER 三类审核 re-grain：目录审核(approve/reject) / 反向草稿(confirm·reject 覆盖) /
    挂接资源(approve/return_for_fix)，capability/gate/basePayload/reasonKey 与 CTA 页一致。"""
    _seed_backlog()
    out = enrich_workbench_backlog({"todos": []}, "ROLE_ORGAN_MANAGER", tenant_id=TENANT)
    todos = {t["id"]: t for t in out["todos"]}

    # 待审核目录
    cat = todos["backlog-catalog-dept-review"]["action"]
    assert cat["kind"] == "decision-list"
    assert {i["id"] for i in cat["items"]} == {"cat-rev-1", "cat-rev-2"}
    assert all(i["capability"] == "catalog.entry.review" for i in cat["items"])
    assert _decision_labels(cat["items"][0]) == ["通过", "驳回"]

    # 待审核反向编目草稿（item 级 capability=confirm，决策逐项覆盖 confirm/reject）
    rev = todos["backlog-reverse-draft-review"]["action"]
    rev_item = rev["items"][0]
    assert rev_item["id"] == "cat-reverse-draft-1"
    assert rev_item["capability"] == "catalog.entry.reverse_draft.confirm"
    confirm, reject = rev_item["decisions"]
    assert confirm["capability"] == "catalog.entry.reverse_draft.confirm"
    assert reject["capability"] == "catalog.entry.reverse_draft.reject"
    assert reject["reasonKey"] == "reject_reason" and reject["needsReason"] is True

    # 待审核挂接资源（resource.asset.review，驳回 = return_for_fix + reason）
    hk = todos["backlog-hookup-review"]["action"]
    hk_item = hk["items"][0]
    assert hk_item["id"] == "res-rev-1"
    assert hk_item["capability"] == "resource.asset.review"
    assert hk_item["basePayload"] == {"resource_code": "res-rev-1"}
    _, hk_reject = hk_item["decisions"]
    assert hk_reject["payload"] == {"decision": "return_for_fix"}
    assert hk_reject["reasonKey"] == "reason" and hk_reject["needsReason"] is True


def test_manager_service_review_todo_has_no_action(temp_db: None) -> None:
    """待审核服务不 re-grain（向导多步）：保 count + href、无 action。"""
    _seed_backlog()
    out = enrich_workbench_backlog({"todos": []}, "ROLE_ORGAN_MANAGER", tenant_id=TENANT)
    todos = {t["id"]: t for t in out["todos"]}
    assert "action" not in todos["backlog-api-review"]
    assert todos["backlog-api-review"]["href"]


def test_manager_m8_filter_applies_to_decision_list_items(temp_db: None) -> None:
    """M8 部门隔离对**行内 item 列表**生效（不只对计数）——越界实体不漏进 decision-list。

    seed owner=_SEED_OWNER；visible_org_codes 不含它（非空集，fail-closed 到域外）→ 三类
    审核待办全部不投（count=0、无空死链）。含它时 → 正常 re-grain 出实体。
    """
    _seed_backlog()
    out_of_scope = {"only-other-org"}
    out = enrich_workbench_backlog(
        {"todos": []}, "ROLE_ORGAN_MANAGER", tenant_id=TENANT, visible_org_codes=out_of_scope
    )
    ids = {t["id"] for t in out["todos"]}
    assert "backlog-catalog-dept-review" not in ids
    assert "backlog-reverse-draft-review" not in ids
    assert "backlog-hookup-review" not in ids

    in_scope = {_SEED_OWNER}
    out2 = enrich_workbench_backlog(
        {"todos": []}, "ROLE_ORGAN_MANAGER", tenant_id=TENANT, visible_org_codes=in_scope
    )
    todos2 = {t["id"]: t for t in out2["todos"]}
    cat_items = todos2["backlog-catalog-dept-review"]["action"]["items"]
    assert {i["id"] for i in cat_items} == {"cat-rev-1", "cat-rev-2"}
    assert all(i["basePayload"]["catalog_code"] in {"cat-rev-1", "cat-rev-2"} for i in cat_items)
