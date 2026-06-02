from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine

import zw_brain.shared.audit as audit_bus
from zw_brain.command.brain import BrainService
from zw_brain.domain.models import Base
from zw_brain.shared.agent_runtime.service import register_brain_provider
from zw_brain.shared.audit.store import StoredAuditEvent, get_default_store
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.db import get_database_url
from zw_brain.shared.migrate import ensure_runtime_schema
from zw_brain.shared.state_store import StateStore

_service: BrainService | None = None
# P1-4: guards the cold-start init below. ThreadingHTTPServer serves each request on its
# own thread, so concurrent first requests could both observe `_service is None` and each
# build a BrainService + run sync_aggregate_tables(full=True) (~528 upserts). Idempotent but
# wasteful and not synchronized. A module-level lock + double-checked `is None` makes init
# happen exactly once.
_service_lock = threading.Lock()


def _make_multiplex_sink(database_store: DatabaseStore):
    """同步多路 sink：一次 emit 同时落到 F1 AuditStore + 主库 audit_event 表。

    写入顺序：先 F1 AuditStore（immutable 文件先落），再主库 audit_event。
    - F1 AuditStore 为 audit.event.query / audit.event.replay (F2) 提供 3 级正规化
      + 多维索引的 SQLite 落点；
    - 主库 audit_event 表保留给 audit.list / capability_call / dashboards 旧消费者；
    任一 sink raise 都视为审计写失败（D4 熔断）。先写 F1 store 保证 audit 不丢——
    若主库 raise，F1 已落（D4 优先）；若 F1 raise，主库不动（两端一致）。
    """
    audit_store = get_default_store()

    def _multiplex(request_id: str, actor: str, skill_id: str, phase: str, payload: dict[str, Any]) -> None:
        audit_store.append(
            StoredAuditEvent(
                request_id=request_id,
                actor=actor,
                skill_id=skill_id,
                tenant_id=str(payload.get("tenant_id") or "sd-default"),
                audit_class=str(payload.get("audit_class") or "read-sensitive"),
                event_type=str(payload.get("event_type") or "capability_call"),
                phase=phase,
                occurred_at=datetime.now(UTC),
                payload=payload,
            )
        )
        database_store.append_audit_event(request_id, actor, skill_id, phase, payload)

    return _multiplex


def get_service() -> BrainService:
    global _service
    # Double-checked locking: the common hot path (service already built) reads the module
    # global with no lock; only the cold-start window takes the lock, and the second
    # `is None` check inside it ensures the heavy init runs exactly once under concurrency.
    if _service is None:
        with _service_lock:
            if _service is None:
                database_store = DatabaseStore()
                database_store.initialize()
                ensure_runtime_schema()
                engine = create_engine(get_database_url(), future=True)
                Base.metadata.create_all(bind=engine)
                audit_bus.configure_sink(_make_multiplex_sink(database_store))
                service = BrainService(state_store=StateStore(database_store=database_store))
                database_store.replace_capability_manifests(service.manifests())
                # Authoritative startup sync (re-asserts every aggregate row); full=True
                # so it ignores the fingerprint cache the constructor already primed and
                # guarantees a complete projection before serving the first request.
                database_store.sync_aggregate_tables(service.snapshot(), full=True)
                # Publish only after init fully completes so a concurrent reader can never
                # observe a partially-initialized service through the global.
                _service = service
    return _service


def reset_service() -> None:
    global _service
    with _service_lock:
        _service = None
        audit_bus.clear_sink()


# IoC wiring: register the brain factory with the embedded agent runtime so that
# shared/agent_runtime never imports command/ (layer order entry→command→domain→shared;
# preflight 段 49). Any path that touches the command layer registers this provider.
register_brain_provider(get_service)
