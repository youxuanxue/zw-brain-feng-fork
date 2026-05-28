"""State sync helpers — Action E module-level functions.

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
   ``demo_state_sync.sync_demo_state_views(brain)`` which reads ~6 snapshot
   keys (provider / zones / workbench / requests / etc.) and calls back into
   ``brain._set_todo_status`` / ``brain._upsert_todo`` /
   ``brain._request_status_text``. ``_sync_request_todos`` similarly walks
   ``brain._snapshot["requests"]`` and writes via ``brain._upsert_todo``.
   These functions must still pass through ``brain`` because the projection
   layer is tightly coupled to BrainService instance attrs and the bypass
   surface (``brain._snapshot`` / ``brain._ui_state``) cannot be lifted out
   without redesigning the snapshot model itself.

Action E scope: lift the 5 helpers into ``sync.py`` module-level functions
with the **minimum-viable signature**. The two pure-IO functions (``persist``
/ ``sync_reference_tables`` / ``sync_database_aggregates``) take explicit
``state_store`` + ``snapshot`` (dict); the three projection functions
(``sync_state_views`` / ``sync_request_todos``) take ``brain`` because the
demo cascade owns that backref. Lifting the brain dependency entirely is
**snapshot-model consolidation debt** (docs/preflight-debt.md 2026-05-28) (snapshot model + ui_state_view consolidation).

BrainService retains a one-line delegate shim per migrated helper so existing
in-process callers (test fixtures, scripts) still work; preflight segment
48 enforces the shim shape.

What lives here
---------------
- ``persist`` — state_store.save(snapshot, ui_state_view).
- ``sync_reference_tables`` — store.sync_reference_tables(snapshot).
- ``sync_database_aggregates`` — store.sync_aggregate_tables(snapshot).
- ``sync_request_todos`` — projects request workbench todos for 4 roles.
- ``sync_state_views`` — composite: sync_request_todos + demo_state_sync cascade.

What stays on BrainService
--------------------------
- ``_upsert_todo`` / ``_set_todo_status`` — in-place writers to
  ``self._snapshot["workbench"]``. They mutate the snapshot dict directly
  and are called from both ``sync_request_todos`` (via brain) and
  ``demo_state_sync`` (via brain). Lifting them out requires the same
  snapshot-model consolidation debt (docs/preflight-debt.md 2026-05-28).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService
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


def sync_database_aggregates(state_store: StateStore, snapshot: dict[str, Any]) -> None:
    """Mirror aggregate-table-shaped snapshot slices into the database_store.

    Replaces ``BrainService._sync_database_aggregates``. Silent skip when
    ``database_store`` is None.
    """
    store = state_store.database_store
    if store is None:
        return
    store.sync_aggregate_tables(snapshot)


# ───────────────────────────────────────────────────────────────────────────
# Projection sync helpers — keep brain backref pending snapshot-model consolidation
# ───────────────────────────────────────────────────────────────────────────


def sync_request_todos(brain: BrainService) -> None:
    """Project request workbench todos for the 4 active roles.

    Replaces ``BrainService._sync_request_todos``. Keeps the ``brain``
    parameter because ``_upsert_todo`` and ``_request_status_text`` are
    instance methods that read/write ``self._snapshot`` and route through
    the request_service. Lifting them out is **snapshot-model consolidation debt** (docs/preflight-debt.md 2026-05-28) — same
    snapshot redesign as ``sync_state_views``.

    R-002/R-005 fix: perspective + category 双维度（perspective 决定文案，
    category 区分同 REQ 在同 role 下的多个待办语境）.
    """
    for request in brain._snapshot["requests"]:
        request_id = request["id"]
        resource_name = request.get("resourceName", request_id)
        brain._upsert_todo(
            "ROLE_ORGAN_OPERATER", request_id,
            f"{resource_name}复用申请进度跟踪",
            brain._request_status_text(request, "applicant"),
            f"#/request-flow/request/{request_id}",
            category="apply-progress",
        )
        brain._upsert_todo(
            "ROLE_ORGAN_MANAGER", request_id,
            f"{resource_name}复用申请待判定",
            brain._request_status_text(request, "reviewer"),
            f"#/request-flow/review/{request_id}",
            category="review",
        )
        if request["status"] in {"supplementing", "summary-pending", "completed", "need-fix"}:
            brain._upsert_todo(
                "ROLE_ORGAN_OPERATER", request_id,
                f"{resource_name}差异补录任务",
                brain._request_status_text(request, "filler"),
                f"#/request-flow/request/{request_id}",
                category="supplement-township",
            )
            brain._upsert_todo(
                "ROLE_ORGAN_OPERATER", request_id,
                f"{resource_name}现场补录任务",
                brain._request_status_text(request, "filler"),
                f"#/request-flow/request/{request_id}",
                category="supplement-village",
            )
        if request["status"] in {"pending", "summary-pending", "completed", "need-fix", "rejected"}:
            brain._upsert_todo(
                "ROLE_ORGAN_MANAGER", request_id,
                f"{resource_name}汇总/准入处理",
                brain._request_status_text(request, "summarizer"),
                f"#/request-flow/review/{request_id}",
                category="summary",
            )


def sync_state_views(brain: BrainService) -> None:
    """Composite snapshot projection — request todos + demo cascade.

    Replaces ``BrainService._sync_state_views``. ``brain`` parameter is
    required because ``demo_state_sync.sync_demo_state_views`` expects a
    BrainService instance (reads ``brain._snapshot``, writes via
    ``brain._set_todo_status``). Pulling the demo cascade off the brain
    reference is **snapshot-model consolidation debt** (docs/preflight-debt.md 2026-05-28) (it would require a registry-of-snapshot-
    writers + state-store-keyed projection model).

    Lazy import breaks the demo_state_sync → brain module cycle.
    """
    sync_request_todos(brain)
    from zw_brain.command.demo_state_sync import sync_demo_state_views  # noqa: PLC0415
    sync_demo_state_views(brain)
