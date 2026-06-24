"""工作台行内决策载荷（workbench inline action）后端守卫.

守护点（契约锁定）：
  - ``upsert_todo`` 传 ``action`` 时把它写进待办；``action is None`` 时不写 ``action`` 键
    （向后兼容，与挂载前逐字一致）。
  - ``sync_request_todos`` 给 BUSIAUDIT 受理待办按 shared_type 挂正确 capability/决策集
    （有条件共享=application.platform_approve 受理/驳回；无条件共享=approval.case.decide
    受理通过/退回补正/驳回），给 MANAGER 部门审核待办挂 application.dept_approve（通过/驳回）。
  - context 行跳过缺失/空源值（不渲染「—」空行），<=6 行。
"""

from __future__ import annotations

from typing import Any

import pytest

from zw_brain.command import sync
from zw_brain.command.demo_state_sync import upsert_todo

pytestmark = pytest.mark.no_db


def _empty_snapshot() -> dict[str, Any]:
    """最小工作台快照——按角色码建空 todos 桶，供投影写入。"""
    roles = ["ROLE_ORGAN_OPERATER", "ROLE_BUSIAUDIT", "ROLE_ORGAN_MANAGER"]
    return {"workbench": {role: {"todos": []} for role in roles}}


# ── upsert_todo action 挂载/省略 ──────────────────────────────────────────────


def test_upsert_todo_omits_action_when_none() -> None:
    snap = _empty_snapshot()
    upsert_todo(snap, "ROLE_BUSIAUDIT", "t1", "标题", "待办", "#/x", category="accept")
    todo = snap["workbench"]["ROLE_BUSIAUDIT"]["todos"][0]
    assert "action" not in todo
    # 形状与挂载前逐字一致。
    assert set(todo) == {"id", "title", "status", "href", "category"}


def test_upsert_todo_carries_action_when_provided() -> None:
    snap = _empty_snapshot()
    action = {"kind": "decision", "capability": "application.dept_approve"}
    upsert_todo(snap, "ROLE_BUSIAUDIT", "t1", "标题", "待办", "#/x", category="accept", action=action)
    todo = snap["workbench"]["ROLE_BUSIAUDIT"]["todos"][0]
    assert todo["action"] == action


def test_upsert_todo_action_on_update_branch() -> None:
    snap = _empty_snapshot()
    upsert_todo(snap, "ROLE_BUSIAUDIT", "t1", "旧", "待办", "#/x", category="accept")
    action = {"kind": "decision", "capability": "approval.case.decide"}
    upsert_todo(snap, "ROLE_BUSIAUDIT", "t1", "新", "待受理", "#/y", category="accept", action=action)
    todos = snap["workbench"]["ROLE_BUSIAUDIT"]["todos"]
    assert len(todos) == 1  # 同 (role,id,category) 更新而非新插
    assert todos[0]["title"] == "新"
    assert todos[0]["action"] == action


# ── sync_request_todos 挂决策载荷 ──────────────────────────────────────────────


class _FakeRecord:
    def __init__(self, payload: dict[str, Any], status: str) -> None:
        self.payload_json = payload
        self.status = status


class _FakeRepo:
    def __init__(self, records: list[_FakeRecord]) -> None:
        self._records = records

    def list_records(self, *, tenant_id: str) -> list[_FakeRecord]:
        return self._records


class _FakeStore:
    def __init__(self, records: list[_FakeRecord]) -> None:
        self.application_repo = _FakeRepo(records)


def _status_text(item: dict[str, Any], perspective: str) -> str:
    return f"{item['status']}/{perspective}"


def _run_sync(records: list[_FakeRecord]) -> dict[str, Any]:
    snap = _empty_snapshot()
    sync.sync_request_todos(snap, _FakeStore(records), _status_text)
    return snap


def _accept_todo(snap: dict[str, Any], request_id: str) -> dict[str, Any]:
    for todo in snap["workbench"]["ROLE_BUSIAUDIT"]["todos"]:
        if todo["id"] == request_id and todo.get("category") == "accept":
            return todo
    raise AssertionError(f"无 {request_id} 受理待办")


def test_accept_conditional_share_uses_platform_approve() -> None:
    # 运行时卡：无 kind（is_runtime_request_payload True）；shared_type=2 → 有条件共享。
    record = _FakeRecord(
        {"id": "REQ-c", "resourceName": "人口库", "applicant": "张三", "purpose": "核验", "shared_type": 2},
        status="submitted",
    )
    snap = _run_sync([record])
    action = _accept_todo(snap, "REQ-c")["action"]
    assert action["kind"] == "decision"
    assert action["capability"] == "application.platform_approve"
    assert action["gate"] == action["capability"]
    assert action["basePayload"] == {"request_id": "REQ-c"}
    labels = [d["label"] for d in action["decisions"]]
    assert labels == ["受理", "驳回"]
    assert action["decisions"][0]["payload"] == {"decision": "approve"}
    assert action["decisions"][1]["payload"] == {"decision": "reject"}
    assert action["decisions"][1]["needsReason"] is True
    assert action["decisions"][1]["reasonKey"] == "note"
    # context：4 行（资源/申请人/用途/共享方式=有条件共享），均有源值。
    ctx = {row["label"]: row["value"] for row in action["context"]}
    assert ctx == {"资源": "人口库", "申请人": "张三", "用途": "核验", "共享方式": "有条件共享"}


def test_accept_unconditional_share_uses_case_decide() -> None:
    # sharedType（驼峰）兜底读取；非 2 → 无条件共享，受理即终三决策。
    record = _FakeRecord(
        {"id": "REQ-u", "resourceName": "证照库", "applicant": "李四", "sharedType": 1},
        status="pending",
    )
    snap = _run_sync([record])
    action = _accept_todo(snap, "REQ-u")["action"]
    assert action["capability"] == "approval.case.decide"
    assert action["gate"] == "approval.case.decide"
    labels = [d["label"] for d in action["decisions"]]
    assert labels == ["受理通过", "退回补正", "驳回"]
    tones = [d["tone"] for d in action["decisions"]]
    assert tones == ["primary", "secondary", "danger"]
    assert action["decisions"][1]["payload"] == {"decision": "return_for_fix"}
    assert action["decisions"][1]["needsReason"] is True
    assert action["decisions"][1]["reasonKey"] == "note"
    assert action["decisions"][2]["needsReason"] is True
    assert action["decisions"][2]["reasonKey"] == "note"
    # context 跳过缺失「用途」行（不渲染「—」空行），保留共享方式=无条件共享。
    ctx = {row["label"]: row["value"] for row in action["context"]}
    assert "用途" not in ctx
    assert ctx["共享方式"] == "无条件共享"


def test_accept_missing_shared_type_defaults_unconditional() -> None:
    record = _FakeRecord({"id": "REQ-d", "resourceName": "库甲"}, status="submitted")
    snap = _run_sync([record])
    action = _accept_todo(snap, "REQ-d")["action"]
    assert action["capability"] == "approval.case.decide"
    ctx = {row["label"]: row["value"] for row in action["context"]}
    assert ctx["共享方式"] == "无条件共享"
    assert "申请人" not in ctx  # 缺失源值 → 跳过


def test_dept_approve_todo_carries_dept_approve_action() -> None:
    # dept_approved 仅出现在有条件共享受理后链路（shared_type==2）。
    record = _FakeRecord(
        {
            "id": "REQ-m",
            "resourceName": "库乙",
            "applicant": "市规划局",
            "purpose": "项目选址核验",
            "shared_type": 2,
        },
        status="dept_approved",
    )
    snap = _run_sync([record])
    review = next(
        t for t in snap["workbench"]["ROLE_ORGAN_MANAGER"]["todos"]
        if t["id"] == "REQ-m" and t.get("category") == "review"
    )
    action = review["action"]
    assert action["kind"] == "decision"
    assert action["capability"] == "application.dept_approve"
    assert action["gate"] == "application.dept_approve"
    assert action["basePayload"] == {"request_id": "REQ-m"}
    labels = [d["label"] for d in action["decisions"]]
    assert labels == ["审核通过", "驳回"]
    assert action["decisions"][0]["payload"] == {"decision": "approve"}
    assert action["decisions"][1]["payload"] == {"decision": "reject"}
    assert action["decisions"][1]["needsReason"] is True
    assert action["decisions"][1]["reasonKey"] == "note"
    # 要点行随载荷下发——审批人展开即见「在审什么」，不必跳详情页（修 _dept_approve_action
    # 原 context=[] 缺口）。
    ctx = {row["label"]: row["value"] for row in action["context"]}
    assert ctx["资源"] == "库乙"
    assert ctx["申请人"] == "市规划局"
    assert ctx["用途"] == "项目选址核验"
    assert ctx["共享方式"] == "有条件共享"


def test_dept_approved_does_not_emit_accept_action() -> None:
    # dept_approved 不在受理态集合 → 不投受理待办（只投部门审核）。
    record = _FakeRecord({"id": "REQ-m2", "resourceName": "库丙"}, status="dept_approved")
    snap = _run_sync([record])
    assert snap["workbench"]["ROLE_BUSIAUDIT"]["todos"] == []


def test_state_transition_prunes_stale_inline_todo() -> None:
    """upsert-only 滞留守卫：受理通过（submitted→dept_approved）后，BUSIAUDIT 受理待办须**剔除**.

    Jobs 隔离栈实测发现：旧 sync upsert-only，单据流转后 accept 待办滞留、且现挂行内 action
    仍可点 → 误对已流转单据再发 platform_approve 报错。在同一快照上前后两次 sync 验证剔除。
    """
    snap = _empty_snapshot()
    payload = {"id": "REQ-t", "resourceName": "人口库", "shared_type": 2}
    # ① 受理态：BUSIAUDIT 出受理待办（携 platform_approve action）。
    sync.sync_request_todos(snap, _FakeStore([_FakeRecord(payload, "submitted")]), _status_text)
    assert _accept_todo(snap, "REQ-t")["action"]["capability"] == "application.platform_approve"
    # ② 流转 dept_approved：同一快照再 sync —— 受理待办剔除、MANAGER 部门审核待办出现。
    sync.sync_request_todos(snap, _FakeStore([_FakeRecord(payload, "dept_approved")]), _status_text)
    busi = snap["workbench"]["ROLE_BUSIAUDIT"]["todos"]
    assert not any(t["id"] == "REQ-t" and t.get("category") == "accept" for t in busi), (
        "受理后 BUSIAUDIT accept 待办应被剔除（不留可点的陈旧受理）"
    )
    mgr = snap["workbench"]["ROLE_ORGAN_MANAGER"]["todos"]
    review = [t for t in mgr if t["id"] == "REQ-t" and t.get("category") == "review"]
    assert len(review) == 1
    assert review[0]["action"]["capability"] == "application.dept_approve"
