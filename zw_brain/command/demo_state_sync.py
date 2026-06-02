"""Snapshot state-sync primitives, decoupled from BrainService (Action H).

General, reusable helpers over the ``snapshot`` dict — ``maybe_*`` lookups,
``set_todo_status`` / ``upsert_todo`` workbench mutators, ``resource_by_id`` /
``zone_by_id`` / ``package_status_text`` — used by the write-path state sync
(``command/sync.py``) and compliance handlers. These take the snapshot dict
directly so callers never reach into a BrainService instance (Action H).

The legacy demo-seed cascade (``sync_demo_state_views``) is **retired** (C-1
删演示单, 2026-06-02): the hardcoded demo 演示单 it projected
(``requests``/``delivery_tasks``/``capability_packages`` 等) are gone from
``seed_snapshot.json`` and reads are single-sourced from DB (#191), so the
cascade had no inputs and was a runtime no-op. Its body was removed so
``scripts/check_no_demo_id_literals.py`` (段36) can forbid demo-id literals
**everywhere** (zero allow-list). The signature is kept as a no-op for the
PersistMiddleware call site (``command/sync.py::sync_state_views``).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from zw_brain.domain.errors import NotFoundError

# ─────────────────────────────────────────────────────────────────────────────
# Snapshot lookup primitives — take snapshot dict, no BrainService instance.
# These mirror the BrainService ``_maybe_*`` / ``_*_by_id`` shape but are
# pure functions over the snapshot dict so demo_state_sync (and sync.py)
# never need to reach back into a BrainService instance.
# ─────────────────────────────────────────────────────────────────────────────


def maybe_request(snapshot: dict[str, Any], request_id: str) -> dict[str, Any] | None:
    """Snapshot request by id; returns None when absent."""
    for item in snapshot["requests"]:
        if item["id"] == request_id:
            return item
    return None


def maybe_delivery(snapshot: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    """Snapshot delivery task by id; returns None when absent."""
    for item in snapshot["delivery_tasks"]:
        if item["id"] == task_id:
            return item
    return None


def maybe_package(snapshot: dict[str, Any], package_id: str) -> dict[str, Any] | None:
    """Snapshot capability package by id; returns None when absent."""
    for item in snapshot.get("packages", []):
        if item.get("id") == package_id:
            return item
    return None


def resource_by_id(snapshot: dict[str, Any], resource_id: str) -> dict[str, Any]:
    """Discovery resource by id; raises NotFoundError when absent."""
    for item in snapshot["discovery"]["resources"]:
        if item["id"] == resource_id:
            return item
    raise NotFoundError(resource_id)


def zone_by_id(snapshot: dict[str, Any], zone_id: str) -> dict[str, Any]:
    """Zone by id; raises NotFoundError when absent."""
    for item in snapshot["zones"]:
        if item["id"] == zone_id:
            return item
    raise NotFoundError(zone_id)


# ─────────────────────────────────────────────────────────────────────────────
# Workbench todo writers — in-place mutators on snapshot["workbench"].
# R-005 fix: 折叠后多个旧角色映射到同一 ROLE_*，原本不同语境的同 item_id 待办若仅按
# (role, item_id) 去重会互相覆盖。引入 category 作为第二维度。
# ─────────────────────────────────────────────────────────────────────────────


def set_todo_status(
    snapshot: dict[str, Any],
    role: str,
    item_id: str,
    status: str,
    *,
    category: str = "",
) -> None:
    """Update existing todo status; no-op if (role, item_id, category) missing.

    Identity tuple: ``(role, item_id, category)``. R-005 fix above.
    """
    bucket = snapshot["workbench"].get(role)
    if not bucket:
        return
    for todo in bucket["todos"]:
        if todo["id"] == item_id and todo.get("category", "") == category:
            todo["status"] = status
            return


def upsert_todo(
    snapshot: dict[str, Any],
    role: str,
    item_id: str,
    title: str,
    status: str,
    href: str,
    *,
    category: str = "",
) -> None:
    """Insert or update a todo under (role, item_id, category)."""
    bucket = snapshot["workbench"].get(role)
    if not bucket:
        return
    for todo in bucket["todos"]:
        if todo["id"] == item_id and todo.get("category", "") == category:
            todo["title"] = title
            todo["status"] = status
            todo["href"] = href
            return
    bucket["todos"].insert(
        0, {"id": item_id, "title": title, "status": status, "href": href, "category": category}
    )


# ─────────────────────────────────────────────────────────────────────────────
# Pure status text helpers — package perspective.
# (request_status_text lives on request_service.status_text — passed in as a
# callback to avoid importing the domain layer from this module.)
# ─────────────────────────────────────────────────────────────────────────────


def package_status_text(item: dict[str, Any]) -> str:
    """Localized package status text."""
    status = item["status"]
    if status == "pending":
        return "待审核"
    if status == "pending-fix":
        return "待补正"
    if status == "approved":
        return "已上线"
    if status == "rejected":
        return "已驳回"
    return str(status)


# ─────────────────────────────────────────────────────────────────────────────
# Demo cascade — main entry. Takes snapshot dict + a pure request status_text
# callback; no BrainService reference.
# ─────────────────────────────────────────────────────────────────────────────


def sync_demo_state_views(
    snapshot: dict[str, Any],
    status_text: Callable[[dict[str, Any], str], str],
) -> None:
    """Retired no-op (C-1 删演示单, 2026-06-02).

    Previously cascaded hardcoded demo-seed 演示单 confirmation state onto
    provider / discovery / zone snapshot slices for the WebUI demo. The demo
    records are gone from ``seed_snapshot.json`` and reads are single-sourced
    from DB (#191), so the cascade had no inputs and was already a runtime
    no-op. Body removed so ``check_no_demo_id_literals.py`` (段36) can forbid
    demo-id literals everywhere (zero allow-list). Signature kept for the
    PersistMiddleware call site (``command/sync.py::sync_state_views``); the
    general helpers above (``set_todo_status`` / ``upsert_todo`` / ``maybe_*`` /
    ``resource_by_id`` / ``zone_by_id``) remain and are used by sync.py /
    compliance handlers.
    """
    _ = (snapshot, status_text)  # retired: no demo cascade
    return None
