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

2. **In-memory snapshot projection** — ``_sync_state_views`` cascades into
   ``demo_state_sync.sync_demo_state_views`` which reads ~6 snapshot keys
   (provider / zones / workbench / requests / etc.) and writes via
   ``set_todo_status`` / ``upsert_todo``. ``_sync_request_todos`` similarly
   walks ``snapshot["requests"]`` and writes via ``upsert_todo``.

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
- ``sync_request_todos`` — projects request workbench todos for 2 roles.
- ``sync_state_views`` — composite: sync_request_todos + demo_state_sync cascade.

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
# Projection sync helpers — Action H: snapshot dict + status_text callback,
# no BrainService reference.
# ───────────────────────────────────────────────────────────────────────────


def sync_request_todos(
    snapshot: dict[str, Any],
    status_text: Callable[[dict[str, Any], str], str],
) -> None:
    """Project request workbench todos per role（受理/审核两级对齐，D55/P21·P21b·P10）.

    Replaces ``BrainService._sync_request_todos``. Action H: takes the
    ``snapshot`` dict directly + a pure ``status_text`` callback (typically
    ``request_service.status_text``). No BrainService reference required.

    R-002/R-005 fix: perspective + category 双维度（perspective 决定文案，
    category 区分同 REQ 在同 role 下的多个待办语境）.

    D55/P21·P21b：受理/审核两级——业务运营员（ROLE_BUSIAUDIT）受理第一级（submitted）、部门管理员
    （ROLE_ORGAN_MANAGER）部门审核第二级（dept_approved）。MANAGER 审核待办由「每单恒投」收敛为
    「仅 dept_approved 单（受理后）才投」，消除受理前误投部门审核待办；业务运营员受理待办深链受理详情。
    注：业务运营员 P1 工作台 todos 由 workbench_backlog_projection.enrich_workbench_backlog 整体现算
    覆盖（待受理申请/异议/需求 + 供数发布），此处对 BUSIAUDIT 的受理待办投影供 P3 受理队列等
    workbench.todos 读侧消费、并与 enrich 口径一致（enrich 仍是 BUSIAUDIT P1 单一事实源）。
    """
    _accept_statuses = {"submitted", "pending"}
    for request in snapshot["requests"]:
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
        if status in _accept_statuses:
            demo_state_sync.upsert_todo(
                snapshot,
                "ROLE_BUSIAUDIT", request_id,
                f"{resource_name}资源申请待受理",
                status_text(request, "reviewer"),
                f"#/request-flow/review/{request_id}",
                category="accept",
            )
        # 第二级部门审核（部门管理员）：仅受理通过待部门审（dept_approved）才投，深链审核详情。
        if status == "dept_approved":
            demo_state_sync.upsert_todo(
                snapshot,
                "ROLE_ORGAN_MANAGER", request_id,
                f"{resource_name}资源申请待审核",
                status_text(request, "reviewer"),
                f"#/request-flow/review/{request_id}",
                category="review",
            )
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
        if request["status"] in {"pending", "summary-pending", "completed", "need-fix", "rejected"}:
            demo_state_sync.upsert_todo(
                snapshot,
                "ROLE_ORGAN_MANAGER", request_id,
                f"{resource_name}汇总/准入处理",
                status_text(request, "summarizer"),
                f"#/request-flow/review/{request_id}",
                category="summary",
            )


def sync_state_views(
    snapshot: dict[str, Any],
    status_text: Callable[[dict[str, Any], str], str],
) -> None:
    """Composite snapshot projection — request todos + demo cascade.

    Replaces ``BrainService._sync_state_views``. Action H: takes the
    ``snapshot`` dict directly + a pure ``status_text`` callback; the demo
    cascade (``demo_state_sync.sync_demo_state_views``) is now fully
    decoupled from the BrainService instance.
    """
    sync_request_todos(snapshot, status_text)
    demo_state_sync.sync_demo_state_views(snapshot, status_text)
