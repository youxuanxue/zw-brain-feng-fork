"""Adapter routing helpers — Action H commit 4 lift from BrainService.

Pure functions that route a ``skill_id`` + payload into:
- ``(adapter_slug, operation, direction)`` — the adapter manifest contract.
- ``aggregate_type`` — the local aggregate kind (catalog / resource / ...).
- ``idempotency_key`` — the dedup key for the adapter capability_call.

These have no state coupling to BrainService. Called only from
``handlers/infra/adapter_passthrough.py``. Lifted out of brain.py so the
adapter routing rules live next to the adapter handler instead of buried
in BrainService.
"""
from __future__ import annotations

from typing import Any


def adapter_operation_from_skill(
    skill_id: str, payload: dict[str, Any]
) -> tuple[str, str, str]:
    """Resolve ``(adapter_slug, operation, direction)`` for an inbound skill_id.

    Replaces ``BrainService._adapter_operation_from_skill``.
    """
    if payload.get("adapter_slug") or payload.get("operation"):
        return (
            str(payload.get("adapter_slug", skill_id.rsplit(".", 1)[0])),
            str(payload.get("operation", skill_id.rsplit(".", 1)[1])),
            str(payload.get("direction", "inbound")),
        )
    if skill_id.startswith("adapter.cascade"):
        operation = "replay" if skill_id.endswith("replay") else "consume"
        return "cascade", operation, str(payload.get("direction", "inbound"))
    if skill_id.startswith("standard.asset"):
        return "standard_asset", skill_id.rsplit(".", 1)[1], str(payload.get("direction", "inbound"))
    if skill_id.startswith("security.scan"):
        return "security_scan", "result_sync", str(payload.get("direction", "inbound"))
    if skill_id.startswith("risk.event"):
        return "risk_event", "ingest", str(payload.get("direction", "inbound"))
    if skill_id.startswith("compliance.signal"):
        return "compliance_signal", "ingest", str(payload.get("direction", "inbound"))
    parts = skill_id.split(".")
    operation = parts[-1]
    if operation in {"pull", "receive", "reconcile", "sync"}:
        direction = "inbound" if operation in {"pull", "receive"} else str(payload.get("direction", "inbound"))
    else:
        direction = str(payload.get("direction", "outbound"))
    return "national", operation, direction


def aggregate_type_from_skill(skill_id: str) -> str:
    """Identify the local aggregate type from the skill_id prefix.

    Replaces ``BrainService._aggregate_type_from_skill``.
    """
    for value in ("catalog", "resource", "application", "delivery", "objection", "topic"):
        if f".{value}." in skill_id:
            return "topic_package" if value == "topic" else value
    return "external"


def adapter_idempotency_key(skill_id: str, payload: dict[str, Any]) -> str:
    """Build a dedup key for an adapter capability_call.

    Replaces ``BrainService._adapter_idempotency_key``.
    """
    return ":".join(
        [
            skill_id,
            str(payload.get("local_aggregate_type") or aggregate_type_from_skill(skill_id)),
            str(
                payload.get("local_aggregate_id")
                or payload.get("external_object_id")
                or payload.get("source_ref")
                or "pending"
            ),
            str(payload.get("external_system") or "national_platform"),
        ]
    )
