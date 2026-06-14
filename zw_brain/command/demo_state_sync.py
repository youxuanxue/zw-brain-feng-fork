"""Snapshot state-sync primitives, decoupled from BrainService (Action H).

General, reusable helpers over the ``snapshot`` dict — ``set_todo_status`` /
``upsert_todo`` workbench mutators, ``resource_by_id`` / ``zone_by_id`` /
``package_status_text`` — used by the write-path state sync
(``command/sync.py``) and compliance handlers. These take the snapshot dict
directly so callers never reach into a BrainService instance (Action H).

History: the demo-seed cascade ``sync_demo_state_views`` was retired (C-1
删演示单, 2026-06-02) and deleted outright by Action D（写路径单源化）；
``maybe_request`` / ``maybe_delivery`` 随 ``requests`` / ``delivery_tasks``
快照键一并退役——申请/审批/交付的单一事实源在 DB（CardSession / service
``by_id`` 读取）。
"""

from __future__ import annotations

from typing import Any

from zw_brain.domain.errors import NotFoundError

# ─────────────────────────────────────────────────────────────────────────────
# Snapshot lookup primitives — take snapshot dict, no BrainService instance.
# Pure functions over the snapshot dict so demo_state_sync (and sync.py) never
# need to reach back into a BrainService instance. The former BrainService
# ``_resource_by_id`` / ``_zone_by_id`` shims that delegated here were零调用 and
# deleted in 死代码清账; callers reach these module-level helpers directly.
# ─────────────────────────────────────────────────────────────────────────────


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


# Demo cascade（C-1 退役 no-op）已随 Action D 整体删除：唯一调用方
# ``sync.sync_state_views`` 不再级联；``maybe_request`` / ``maybe_delivery``
# 快照查找原语随 requests / delivery_tasks 快照键退役（DB 单一事实源，经
# CardSession / 各 service by_id）。
