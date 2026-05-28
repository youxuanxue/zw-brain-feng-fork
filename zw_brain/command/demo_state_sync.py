"""Demo-seed state cascades, decoupled from BrainService (Action H).

These blocks react to the ``sd-default`` demo seed entities (the parking-lot
reuse journey: ``REQ-2026-04-25-0011`` / ``DLV-2026-04-25-0011`` /
``PKG-2026-04-25-001`` / ``res-jbxx-ledger`` / ...) and project their
confirmation state onto provider / discovery / zone snapshot slices for the
WebUI demo.

They used to live inline in ``BrainService._sync_state_views`` and ran on every
mutation. The behavior is unchanged — under a real customer seed these IDs don't
exist, so each ``maybe_*`` lookup returns ``None`` and the cascade is a no-op.
Keeping them in a clearly-named module (rather than the core state machine) is
the point: ``scripts/check_no_demo_id_literals.py`` forbids these literals from
leaking back into ``brain.py`` / handlers, and this file is the single
allow-listed home.

Action H change
---------------
Before Action H ``sync_demo_state_views(brain)`` reached into the BrainService
instance via ``brain._maybe_request`` / ``brain._set_todo_status`` /
``brain._snapshot["provider"]`` etc. — three SoT (in-memory dict + state_store
file + database_store SQL) bound together through the BrainService instance.

Action H lifts the lookup / mutation primitives into module-level functions
that take the ``snapshot`` dict directly. ``sync_demo_state_views`` now accepts
``(snapshot, status_text)`` — the snapshot dict is mutated in place; the
``status_text`` callback (typically ``request_service.status_text``) stays a
pure function ``(item, perspective) -> str`` and is passed in so this module
does not import the domain service layer (avoids cycles).

BrainService still owns the snapshot dict (``self._snapshot``) as the
lifecycle / persistence anchor; this module no longer cares which instance
that is.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import zw_brain.shared.clock as clock
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
    """Project demo-seed confirmation state onto provider / discovery / zone slices.

    Mutates ``snapshot`` in place. Under a real customer seed (no
    REQ-2026-04-25-0011 etc.) all ``maybe_*`` lookups return None and the
    cascade is a no-op.

    Parameters
    ----------
    snapshot:
        The BrainService snapshot dict (``brain._snapshot``). Mutated in place.
    status_text:
        Pure callback ``(item, perspective) -> str``; typically
        ``request_service.status_text``. Kept as a parameter rather than an
        import to prevent a demo_state_sync → domain.services cycle.
    """
    request0011 = maybe_request(snapshot, "REQ-2026-04-25-0011")
    request0007 = maybe_request(snapshot, "REQ-2026-04-24-0007")
    task0011 = maybe_delivery(snapshot, "DLV-2026-04-25-0011")
    package001 = maybe_package(snapshot, "PKG-2026-04-25-001")

    if request0011:
        # R-005 fix: 每条待办按 (role, item_id, category) 唯一；同一 REQ ID 在同一 role 下可承载多语境
        set_todo_status(snapshot, "ROLE_ORGAN_OPERATER", "REQ-2026-04-25-0011", status_text(request0011, "applicant"), category="apply-progress")
        set_todo_status(snapshot, "ROLE_ORGAN_MANAGER", "REQ-2026-04-25-0011", status_text(request0011, "reviewer"), category="review")
        set_todo_status(snapshot, "ROLE_ORGAN_OPERATER", "REQ-2026-04-25-0011", status_text(request0011, "filler"), category="supplement-township")
        set_todo_status(snapshot, "ROLE_ORGAN_OPERATER", "REQ-2026-04-25-0011", status_text(request0011, "filler"), category="supplement-village")
        set_todo_status(snapshot, "ROLE_ORGAN_MANAGER", "REQ-2026-04-25-0011", status_text(request0011, "summarizer"), category="summary")
    if request0007:
        set_todo_status(snapshot, "ROLE_ORGAN_MANAGER", "REQ-2026-04-24-0007", status_text(request0007, "reviewer"), category="review")
        set_todo_status(snapshot, "ROLE_ORGAN_OPERATER", "REQ-2026-04-24-0007", status_text(request0007, "filler"), category="supplement-township")

    if task0011:
        confirmed = task0011["backflow"]["status"] == "已确认"
        set_todo_status(snapshot, "ROLE_ORGAN_MANAGER", "LEDGER-parking-v1.3", "已发布" if confirmed else "待发布")
        set_todo_status(snapshot, "ROLE_BUSIAUDIT", "ZONE-business-ledger", "已上线" if confirmed else "待更新")
        provider = snapshot["provider"]
        provider["overview"][0]["value"] = "v1.3" if confirmed else "v1.2 → v1.3"
        provider["overview"][2]["value"] = "0" if confirmed else str(len(task0011["backflow"]["candidateFields"]))
        provider["catalogs"][0]["issue"] = "v1.3 版本说明已同步" if confirmed else "需补充 v1.3 版本说明"
        if not provider["catalogs"][1].get("governanceLocked"):
            provider["catalogs"][1]["status"] = "已发布" if confirmed else "待质检"
            provider["catalogs"][1]["issue"] = "默认复用入口已更新" if confirmed else "需更新默认复用入口说明"
        provider["resources"][0]["updatedAt"] = clock.now_date() if confirmed else "2026-04-25"
        if not provider["resources"][1].get("governanceLocked"):
            provider["resources"][1]["status"] = "可共享" if confirmed else "待审核"
        provider["aiGovernance"]["summary"] = (
            "停车场信息共享目录已确认吸收高频差异字段，下一步重点转为持续监测补录热区和维护专题入口一致性。"
            if confirmed
            else "建议优先发布停车场信息共享目录回流候选，并把“本地泊位开放状态”“最新开放时间”纳入目录说明；其次更新城市运行专题目录中的默认复用入口说明。"
        )
        discovery = resource_by_id(snapshot, "res-jbxx-ledger")
        discovery["coverage"] = "89%" if confirmed else "82%"
        discovery["updatedAt"] = clock.now_date() if confirmed else "2026-04-25"
        discovery["explain"] = [
            "当前需求可直接复用 v1.3 模板，基层补录字段进一步收缩",
            "经营状态与最近走访时间已纳入正式字段",
            "专题入口与模板版本已同步更新",
        ] if confirmed else [
            "当前需求首先应复用该模板，而不是重新发起整表采集",
            "模板已覆盖多数企业基础字段",
            "仅需补少量现场差异字段即可形成任务",
        ]
        zone = zone_by_id(snapshot, "business")
        zone["trust"] = [
            "来源等级：高",
            "模板版本：v1.3，默认入口已同步",
            "责任方：区政数局 / 市场监管局",
        ] if confirmed else [
            "来源等级：高",
            "模板版本：v1.2，v1.3 待发布",
            "责任方：区政数局 / 市场监管局",
        ]
        # K12 dashboard 块已退役（详见 D15 二次反转）；toggle 副作用不再更新大屏 burden/suggestions

    if package001:
        set_todo_status(snapshot, "ROLE_BUSIAUDIT", "PKG-2026-04-25-001", package_status_text(package001))
