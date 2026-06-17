"""State sync helpers — Action E module-level functions; Action H snapshot decoupling.

Background
----------
Before Action E, the 5 state-sync helpers (``_persist`` /
``_sync_reference_tables`` / ``_sync_database_aggregates`` /
``_sync_state_views`` / ``_sync_request_todos``) lived as private methods on
``BrainService``. They straddle two concerns:

1. **State store I/O** — ``_persist`` writes snapshot + ui_state to disk;
   ``_sync_reference_tables`` / ``_sync_database_aggregates`` mirror selected
   snapshot keys into reference + aggregate tables in the database_store.
   These are pure functions of ``(state_store, snapshot, ui_state_view)`` —
   no implicit ``self.brain`` backref needed.

2. **Workbench todo projection** — ``sync_request_todos`` 按库现算
   （Action D：走 ``application_record`` 运行时卡，demo cascade 已删），
   写 ``snapshot["workbench"]`` via ``upsert_todo``。

Action E lifted (1) into module-level functions (``persist`` /
``sync_reference_tables`` / ``sync_database_aggregates``); Action H now lifts
(2) too — ``sync_state_views`` and ``sync_request_todos`` take the
``snapshot`` dict directly + a ``status_text`` callback (the projection
primitives live in :mod:`zw_brain.command.demo_state_sync` as
``set_todo_status`` / ``upsert_todo`` etc.). Neither function needs a
``BrainService`` reference anymore.

BrainService retains a one-line delegate shim per migrated helper so existing
in-process callers (test fixtures, scripts) still work; preflight segment 48
enforces the shim shape.

What lives here
---------------
- ``persist`` — state_store.save(snapshot, ui_state_view).
- ``sync_reference_tables`` — store.sync_reference_tables(snapshot).
- ``sync_database_aggregates`` — store.sync_aggregate_tables(snapshot).
- ``sync_request_todos`` — 按 application_record 现算工作台待办（Action D）。
- ``sync_state_views`` — 同上的组合入口（demo cascade 已随 Action D 删除）。

What stays on BrainService
--------------------------
- ``_snapshot`` / ``_ui_state`` / ``_state_store`` — lifecycle owners.
- ``_set_todo_status`` / ``_upsert_todo`` / ``_request_status_text`` /
  ``_package_status_text`` — kept as 1-line shims to the demo_state_sync
  module-level functions for back-compat (handlers in compliance.py and
  catalog_meta.py still spell them via ``brain.X``; Action H scope keeps the
  shim names rather than rewriting the handlers in the same commit).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from zw_brain.command import demo_state_sync

if TYPE_CHECKING:
    from zw_brain.shared.state_store import StateStore


# ───────────────────────────────────────────────────────────────────────────
# Pure-IO sync helpers — no brain backref
# ───────────────────────────────────────────────────────────────────────────


def persist(state_store: StateStore, snapshot: dict[str, Any], ui_state_view: dict[str, Any]) -> None:
    """Persist the in-memory snapshot + ui_state to the state store.

    Replaces ``BrainService._persist``. ``ui_state_view`` is the result of
    ``brain._ui_state.persistable_view()`` — callers pass the materialized
    view so this function stays decoupled from the ``_UIStateProxy`` shape.
    """
    state_store.save(snapshot, ui_state_view)


def sync_reference_tables(state_store: StateStore, snapshot: dict[str, Any]) -> None:
    """Mirror reference-table-shaped snapshot slices into the database_store.

    Replaces ``BrainService._sync_reference_tables``. Silent skip when
    ``database_store`` is None (legacy in-memory mode).
    """
    store = state_store.database_store
    if store is None:
        return
    store.sync_reference_tables(snapshot)


def sync_database_aggregates(state_store: StateStore, snapshot: dict[str, Any], *, full: bool = False) -> None:
    """Mirror aggregate-table-shaped snapshot slices into the database_store.

    Replaces ``BrainService._sync_database_aggregates``. Silent skip when
    ``database_store`` is None.

    ``full=True`` (startup / authoritative sync) forces every entity to be
    upserted and primes the fingerprint cache; the per-write hot path uses the
    default ``full=False`` so each write only re-syncs the entities it changed
    (HIGH-2). On a cold store the delta path is already complete (every entity
    is a cache miss), so ``full`` only matters as an explicit "re-assert all
    rows, ignoring cached fingerprints" on an already-warm store.
    """
    store = state_store.database_store
    if store is None:
        return
    store.sync_aggregate_tables(snapshot, full=full)


# ───────────────────────────────────────────────────────────────────────────
# Inline-action payload builders — 给「简单是/否型审核待办」挂自描述决策载荷
# （workbench inline action contract）。capability/gate 均为既有 skillId
# （dispatch.py 已注册），不新铸标识符。
# ───────────────────────────────────────────────────────────────────────────

# 有条件共享码：dsp_catalog shared_type==2（与 catalog_entry / request handler 同源口径）。
_CONDITIONAL_SHARE_TYPE = 2


def _decision_context(request: dict[str, Any], shared_type: int) -> list[dict[str, str]]:
    """组装行内决策面板的上下文行（<=6 行，源值缺失/空则跳过该行——不渲染「—」空行）。"""
    rows: list[tuple[str, Any]] = [
        ("资源", request.get("resourceName")),
        ("申请人", request.get("applicant")),
        ("用途", request.get("purpose")),
        ("共享方式", "有条件共享" if shared_type == _CONDITIONAL_SHARE_TYPE else "无条件共享"),
    ]
    return [{"label": label, "value": str(value)} for label, value in rows if value]


def _dept_approve_action(request: dict[str, Any], request_id: str) -> dict[str, Any]:
    """部门管理员申请部门审核（dept_approved）的行内决策载荷（通过 / 驳回）。

    dept_approved 仅出现在有条件共享（shared_type==2，受理后转部门审）链路，故要点行
    照 ``_decision_context`` 现算（资源/申请人/用途/共享方式）——审批人展开即见「在审什么」，
    不必跳详情页读六行字。
    """
    capability = "application.dept_approve"
    shared_type = int(request.get("shared_type", request.get("sharedType", 0)) or 0)
    return {
        "kind": "decision",
        "capability": capability,
        "gate": capability,
        "basePayload": {"request_id": request_id},
        "context": _decision_context(request, shared_type),
        "decisions": [
            {"label": "审核通过", "tone": "primary", "success": "审核通过（已授权）", "payload": {"decision": "approve"}},
            {"label": "驳回", "tone": "danger", "success": "部门审核驳回", "payload": {"decision": "reject"}},
        ],
    }


def _accept_action(request: dict[str, Any], request_id: str) -> dict[str, Any]:
    """业务运营员申请受理的行内决策载荷，按 shared_type 选 capability 与决策集.

    有条件共享（shared_type==2，受理后待部门审）→ application.platform_approve（受理/驳回）；
    无条件共享（受理即终）→ approval.case.decide（受理通过/退回补正/驳回）。
    """
    shared_type = int(request.get("shared_type", request.get("sharedType", 0)) or 0)
    context = _decision_context(request, shared_type)
    if shared_type == _CONDITIONAL_SHARE_TYPE:
        capability = "application.platform_approve"
        decisions = [
            {"label": "受理", "tone": "primary", "success": "已受理（待部门审核）", "payload": {"decision": "approve"}},
            {"label": "驳回", "tone": "danger", "success": "受理驳回", "payload": {"decision": "reject"}},
        ]
    else:
        capability = "approval.case.decide"
        decisions = [
            {"label": "受理通过", "tone": "primary", "success": "已通过", "payload": {"decision": "approve"}},
            {"label": "退回补正", "tone": "secondary", "success": "已退回补正", "payload": {"decision": "return_for_fix"}},
            {"label": "驳回", "tone": "danger", "success": "已驳回", "payload": {"decision": "reject"}},
        ]
    return {
        "kind": "decision",
        "capability": capability,
        "gate": capability,
        "basePayload": {"request_id": request_id},
        "context": context,
        "decisions": decisions,
    }


# ───────────────────────────────────────────────────────────────────────────
# Projection sync helpers — Action H: snapshot dict + status_text callback,
# no BrainService reference.
# ───────────────────────────────────────────────────────────────────────────


def sync_request_todos(
    snapshot: dict[str, Any],
    store: Any,
    status_text: Callable[[dict[str, Any], str], str],
) -> None:
    """Project request workbench todos per role（受理/审核两级对齐，D55/P21·P21b·P10）.

    Action D：申请单一事实源在 ``application_record``——本投影按库现算
    （运行时卡 payload + 权威 status 列；legacy 导入单不投待办，与退役前
    快照语义一致），写进 snapshot["workbench"]。``store`` 为 None（无库
    模式）时安静跳过。

    R-002/R-005 fix: perspective + category 双维度（perspective 决定文案，
    category 区分同申请在同 role 下的多个待办语境）.

    D55/P21·P21b：受理/审核两级——业务运营员（ROLE_BUSIAUDIT）受理第一级（submitted）、部门管理员
    （ROLE_ORGAN_MANAGER）部门审核第二级（dept_approved）。MANAGER 审核待办由「每单恒投」收敛为
    「仅 dept_approved 单（受理后）才投」，消除受理前误投部门审核待办；业务运营员受理待办深链受理详情。
    注：业务运营员 P1 工作台 todos 由 workbench_backlog_projection.enrich_workbench_backlog 整体现算
    覆盖（待受理申请/异议/需求 + 供数发布），此处对 BUSIAUDIT 的受理待办投影供 P3 受理队列等
    workbench.todos 读侧消费、并与 enrich 口径一致（enrich 仍是 BUSIAUDIT P1 单一事实源）。
    """
    if store is None:
        return
    from zw_brain.command.card_session import is_runtime_request_payload  # noqa: PLC0415
    from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID  # noqa: PLC0415

    _accept_statuses = {"submitted", "pending"}
    for record in store.application_repo.list_records(tenant_id=DEFAULT_TENANT_ID):
        if not is_runtime_request_payload(record.payload_json):
            continue
        request = dict(record.payload_json)
        request["status"] = record.status
        request_id = request["id"]
        resource_name = request.get("resourceName", request_id)
        status = request["status"]
        demo_state_sync.upsert_todo(
            snapshot,
            "ROLE_ORGAN_OPERATER", request_id,
            f"{resource_name}资源申请进度跟踪",
            status_text(request, "applicant"),
            f"#/request-flow/request/{request_id}",
            category="apply-progress",
        )
        # 第一级受理（业务运营员）：申请进入受理态（submitted/pending）→ 受理待办，深链受理详情。
        # 挂行内决策载荷（受理/驳回，按 shared_type 选 capability），供前端展开成内联受理面板。
        # upsert-only 会让状态流转后旧待办滞留：单据离开受理态（如已受理转 dept_approved）须**剔除**
        # BUSIAUDIT accept 待办，否则行内 action 仍可点 → 对已流转单据再发 platform_approve 报错。
        if status in _accept_statuses:
            demo_state_sync.upsert_todo(
                snapshot,
                "ROLE_BUSIAUDIT", request_id,
                f"{resource_name}资源申请待受理",
                status_text(request, "reviewer"),
                f"#/request-flow/review/{request_id}",
                category="accept",
                action=_accept_action(request, request_id),
            )
        else:
            demo_state_sync.remove_todo(snapshot, "ROLE_BUSIAUDIT", request_id, category="accept")
        # 第二级部门审核（部门管理员）：仅受理通过待部门审（dept_approved）才投，深链审核详情。
        # 挂行内决策载荷（审核通过/驳回），供前端展开成内联部门审核面板；离开 dept_approved 须剔除。
        if status == "dept_approved":
            demo_state_sync.upsert_todo(
                snapshot,
                "ROLE_ORGAN_MANAGER", request_id,
                f"{resource_name}资源申请待审核",
                status_text(request, "reviewer"),
                f"#/request-flow/review/{request_id}",
                category="review",
                action=_dept_approve_action(request, request_id),
            )
        else:
            demo_state_sync.remove_todo(snapshot, "ROLE_ORGAN_MANAGER", request_id, category="review")
        if request["status"] in {"supplementing", "summary-pending", "completed", "need-fix"}:
            demo_state_sync.upsert_todo(
                snapshot,
                "ROLE_ORGAN_OPERATER", request_id,
                f"{resource_name}差异补录任务",
                status_text(request, "filler"),
                f"#/request-flow/request/{request_id}",
                category="supplement-township",
            )
            demo_state_sync.upsert_todo(
                snapshot,
                "ROLE_ORGAN_OPERATER", request_id,
                f"{resource_name}现场补录任务",
                status_text(request, "filler"),
                f"#/request-flow/request/{request_id}",
                category="supplement-village",
            )
        else:
            demo_state_sync.remove_todo(snapshot, "ROLE_ORGAN_OPERATER", request_id, category="supplement-township")
            demo_state_sync.remove_todo(snapshot, "ROLE_ORGAN_OPERATER", request_id, category="supplement-village")
        if request["status"] in {"pending", "summary-pending", "completed", "need-fix", "rejected"}:
            demo_state_sync.upsert_todo(
                snapshot,
                "ROLE_ORGAN_MANAGER", request_id,
                f"{resource_name}汇总/准入处理",
                status_text(request, "summarizer"),
                f"#/request-flow/review/{request_id}",
                category="summary",
            )
        else:
            demo_state_sync.remove_todo(snapshot, "ROLE_ORGAN_MANAGER", request_id, category="summary")


def sync_state_views(
    snapshot: dict[str, Any],
    store: Any,
    status_text: Callable[[dict[str, Any], str], str],
) -> None:
    """Composite projection — request workbench todos（Action D：按库现算）.

    Replaces ``BrainService._sync_state_views``. ``store`` 是
    ``state_store.database_store``（None = 无库模式，跳过投影）。demo
    cascade 已退役（C-1），不再级联。
    """
    sync_request_todos(snapshot, store, status_text)
