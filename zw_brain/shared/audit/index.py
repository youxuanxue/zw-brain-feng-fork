"""Audit query / replay index — read-side facade on top of AuditStore.

F1 提供 Python 查询 API；F2 的 audit.event.query / audit.event.replay
capability 会把这个模块包成 skill handler。F1 不在这里建 capability，避免与
F2 scope 重叠。

只读侧，所有写操作走 store.AuditStore.append。
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from zw_brain.shared.audit.store import (
    AuditStore,
    StoredAuditEvent,
    get_default_store,
)


def query(
    *,
    store: AuditStore | None = None,
    actor: str | None = None,
    skill_id: str | None = None,
    tenant_id: str | None = None,
    audit_class: str | None = None,
    request_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 200,
) -> list[StoredAuditEvent]:
    """按常用维度查询审计事件，按 occurred_at 升序返回。

    所有维度均可省略；维度全空时返回最近的 ``limit`` 条（默认 200）。store 默认走
    ``get_default_store()``，单测可显式注入临时 store。
    """
    target = store or get_default_store()
    return target.query(
        actor=actor,
        skill_id=skill_id,
        tenant_id=tenant_id,
        audit_class=audit_class,
        request_id=request_id,
        since=since,
        until=until,
        limit=limit,
    )


def query_outcome_rows(
    *,
    store: AuditStore | None = None,
    tenant_id: str | None = None,
    audit_class: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 10000,
) -> list[tuple]:
    """轻量行查询（不水合 payload）——异常扫描专用，见 AuditStore.query_outcome_rows。"""
    target = store or get_default_store()
    return target.query_outcome_rows(
        tenant_id=tenant_id, audit_class=audit_class, since=since, until=until, limit=limit
    )


def list_by_request_id(
    request_id: str,
    *,
    store: AuditStore | None = None,
    limit: int = 200,
) -> list[StoredAuditEvent]:
    """按 request_id 拉一条审批链的全部事件（F2 回放主入口）。"""
    return query(store=store, request_id=request_id, limit=limit)


def summarize(events: Iterable[StoredAuditEvent]) -> dict[str, Any]:
    """对一批事件做最小聚合，用于 F3 dashboards / B1.1 panel 的预聚合。

    返回结构：
      {
        "total": N,
        "by_audit_class": {"write-critical": x, ...},
        "by_skill": {"...": n, ...},
        "by_actor": {"...": n, ...},
        "first_occurred_at": isoformat | None,
        "last_occurred_at": isoformat | None,
      }
    """
    total = 0
    by_class: dict[str, int] = {}
    by_skill: dict[str, int] = {}
    by_actor: dict[str, int] = {}
    first: datetime | None = None
    last: datetime | None = None
    for ev in events:
        total += 1
        by_class[ev.audit_class] = by_class.get(ev.audit_class, 0) + 1
        by_skill[ev.skill_id] = by_skill.get(ev.skill_id, 0) + 1
        by_actor[ev.actor] = by_actor.get(ev.actor, 0) + 1
        if first is None or ev.occurred_at < first:
            first = ev.occurred_at
        if last is None or ev.occurred_at > last:
            last = ev.occurred_at
    return {
        "total": total,
        "by_audit_class": by_class,
        "by_skill": by_skill,
        "by_actor": by_actor,
        "first_occurred_at": first.isoformat() if first else None,
        "last_occurred_at": last.isoformat() if last else None,
    }
