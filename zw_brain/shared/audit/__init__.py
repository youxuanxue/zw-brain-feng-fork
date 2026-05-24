"""Synchronous durable audit bus — production event stream (F1 of e4-b1-agentruntime).

公共 API（与历史保持兼容）：
    AuditEvent / AuditWriteError / emit / configure_sink / clear_sink / drain

新增（F1）：
    - AuditEvent.tenant_id / audit_class / event_type 三个字段
    - audit_class 在 emit 处做 3 级正规化（write-critical / write-normal /
      read-sensitive，详见 docs/audit-class-normalization.md）
    - 独立 SQLite store（zw_brain.shared.audit.store）+ query API
      (zw_brain.shared.audit.index)
    - 仍要求 ``configure_sink`` 注入 durable sink；emit 同时把事件追加到 sink
      和模块内 buffer，sink 失败硬熔断（D4 「审计写入失败必须熔断」）

边界（F1 不做）：
    - audit.event.query / audit.event.replay capability skill —— F2
    - B1.1 4 panel UI —— F3
    - 区块链锚定真实对接 —— E6 / M0，本模块在 store 留 ``post_persist_hook`` 钩子
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from zw_brain.shared.audit.store import (
    CANONICAL_AUDIT_CLASSES,
    AuditWriteError,
    StoredAuditEvent,
    normalize_audit_class,
)

__all__ = (
    "AuditEvent",
    "AuditWriteError",
    "CANONICAL_AUDIT_CLASSES",
    "StoredAuditEvent",
    "clear_sink",
    "configure_sink",
    "drain",
    "emit",
    "normalize_audit_class",
)

# Sink 签名延续历史 5-tuple，让既有 runtime.configure_sink(database_store.append_audit_event)
# 不用改一行就能继续工作。F1 在 emit 处把 audit_class normalize 后写入 payload，所以
# 下游 sink 看到的 payload 必然已包含规范化字段。
_SinkCallable = Callable[[str, str, str, str, dict[str, Any]], None]

_buffer: list[AuditEvent] = []
_sink: _SinkCallable | None = None


@dataclass(frozen=True)
class AuditEvent:
    request_id: str
    actor: str
    skill_id: str
    phase: str
    payload: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    # F1 新增字段：默认值保证旧调用点 (BrainService._record_audit) 不必改一行
    tenant_id: str | None = None
    audit_class: str | None = None
    event_type: str | None = None


def configure_sink(sink: _SinkCallable) -> None:
    global _sink
    _sink = sink


def clear_sink() -> None:
    global _sink
    _sink = None


def emit(event: AuditEvent) -> None:
    """同步派发一条审计事件。

    - 必填字段缺失 → AuditWriteError
    - 未配置 sink → AuditWriteError（D4 「不允许无审计落库」）
    - sink 调用失败 → AuditWriteError 包裹后重抛（D4 熔断）
    - audit_class 走 normalize_audit_class，规范化值写回 payload[audit_class]，
      原值同步保留到 payload[original_audit_class]（与 store.append 一致）
    """
    if not event.request_id or not event.actor or not event.skill_id:
        raise AuditWriteError(
            "audit_event missing required fields (request_id/actor/skill_id)"
        )
    if _sink is None:
        raise AuditWriteError("durable audit sink is not configured")

    # 入 sink 前对 payload 做最小规范化，让所有下游（database_store / 独立
    # AuditStore / dashboards）看到一致的 3 级 audit_class。
    raw_audit_class = event.audit_class or event.payload.get("audit_class")
    normalized = normalize_audit_class(raw_audit_class)
    enriched_payload = dict(event.payload)
    enriched_payload["audit_class"] = normalized
    if raw_audit_class and raw_audit_class != normalized:
        enriched_payload.setdefault("original_audit_class", raw_audit_class)
    if event.tenant_id:
        enriched_payload.setdefault("tenant_id", event.tenant_id)
    if event.event_type:
        enriched_payload.setdefault("event_type", event.event_type)

    try:
        _sink(event.request_id, event.actor, event.skill_id, event.phase, enriched_payload)
    except Exception as exc:  # noqa: BLE001 -- 任何 sink 异常都必须熔断业务
        raise AuditWriteError(str(exc)) from exc

    _buffer.append(
        AuditEvent(
            request_id=event.request_id,
            actor=event.actor,
            skill_id=event.skill_id,
            phase=event.phase,
            payload=enriched_payload,
            occurred_at=event.occurred_at,
            tenant_id=event.tenant_id,
            audit_class=normalized,
            event_type=event.event_type,
        )
    )


def drain() -> list[AuditEvent]:
    out, _buffer[:] = list(_buffer), []
    return out
