from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from zw_brain.domain.models import AgentRuntimeAgentStateRecord
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.sanitization import safe_json

_SCHEMA_READY = False
_SCHEMA_LOCK = threading.Lock()


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def _now() -> datetime:
    return _utc_naive(datetime.now(UTC))


def _ensure_schema_ready() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        _SCHEMA_READY = True


class AgentRuntimeStateRepository:
    def list_states(self, *, tenant_id: str = "sd-default") -> dict[str, AgentRuntimeAgentStateRecord]:
        _ensure_schema_ready()
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            rows = session.execute(
                select(AgentRuntimeAgentStateRecord)
                .where(AgentRuntimeAgentStateRecord.tenant_id == tenant_id)
                .order_by(AgentRuntimeAgentStateRecord.agent_id)
            ).scalars()
            return {row.agent_id: row for row in rows}

    def get_state(self, agent_id: str, *, tenant_id: str = "sd-default") -> AgentRuntimeAgentStateRecord | None:
        _ensure_schema_ready()
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return session.execute(
                select(AgentRuntimeAgentStateRecord).where(
                    AgentRuntimeAgentStateRecord.tenant_id == tenant_id,
                    AgentRuntimeAgentStateRecord.agent_id == agent_id,
                )
            ).scalar_one_or_none()

    def set_state(
        self,
        agent_id: str,
        *,
        tenant_id: str = "sd-default",
        enabled: bool,
        allowed_roles: list[str],
        updated_by: str | None,
        reason: str | None,
    ) -> AgentRuntimeAgentStateRecord:
        _ensure_schema_ready()
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(
                select(AgentRuntimeAgentStateRecord).where(
                    AgentRuntimeAgentStateRecord.tenant_id == tenant_id,
                    AgentRuntimeAgentStateRecord.agent_id == agent_id,
                )
            ).scalar_one_or_none()
            if record is None:
                record = AgentRuntimeAgentStateRecord(
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    enabled=enabled,
                    allowed_roles_json=safe_json(list(allowed_roles)),
                    updated_by=updated_by,
                    reason=reason,
                    updated_at=_now(),
                )
                session.add(record)
            else:
                record.enabled = enabled
                record.allowed_roles_json = safe_json(list(allowed_roles))
                record.updated_by = updated_by
                record.reason = reason
                record.updated_at = _now()
            session.commit()
            session.refresh(record)
            return record

    @staticmethod
    def to_dict(record: AgentRuntimeAgentStateRecord | None, *, default_roles: list[str]) -> dict[str, Any]:
        if record is None:
            return {
                "enabled": True,
                "allowed_roles": list(default_roles),
                "updated_by": None,
                "reason": None,
                "updated_at": None,
            }
        roles = record.allowed_roles_json if isinstance(record.allowed_roles_json, list) else []
        return {
            "enabled": bool(record.enabled),
            "allowed_roles": [str(role) for role in roles],
            "updated_by": record.updated_by,
            "reason": record.reason,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }
