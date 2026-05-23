from __future__ import annotations

import copy
from typing import Any

SENSITIVE_JSON_KEYS = {
    "secret",
    "password",
    "passwd",
    "token",
    "credential",
    "app_secret",
    "superior_app_secret",
    "api_key",
    "access_token",
    "refresh_token",
    "client_secret",
    "authorization",
    "cookie",
    "session",
    "session_id",
    "session_key",
    "secret_key",
    "certificate",
    "cert",
    "private_key",
    "permission_sql",
    "service_sql",
    # Process-local trust marker (zw_brain.shared.session_context._TRUSTED_SESSION_MARKER).
    # Carrying its object() sentinel into any serialization sink (audit DB, log, JSON
    # response) raises TypeError. The marker is only meaningful inside one process and
    # MUST NOT cross a serialization boundary.
    "_trusted_session_context",
}


def _is_sensitive_json_key(key: object) -> bool:
    lowered = str(key).lower()
    return (
        lowered in SENSITIVE_JSON_KEYS
        or lowered.endswith("_token")
        or lowered.endswith("_secret")
        or lowered.endswith("_key")
        or "password" in lowered
        or "credential" in lowered
        or "authorization" in lowered
        or lowered.endswith("_sql")
        or lowered in {"session", "passwd"}
    )


def safe_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: safe_json(item)
            for key, item in copy.deepcopy(value).items()
            if not _is_sensitive_json_key(key)
        }
    if isinstance(value, list):
        return [safe_json(item) for item in copy.deepcopy(value)]
    return copy.deepcopy(value)


def adapter_source_kind(source_ref: Any) -> str:
    source = str(source_ref or "")
    source_norm = source.lower()
    if "audit" in source_norm or "capability_call" in source_norm:
        return "audit_event"
    if "gateway_log" in source_norm or "gateway-log" in source_norm or "/openapi/report" in source_norm or "gateway_report" in source_norm:
        return "gateway_adapter"
    if "api_service_times" in source_norm or "api_service_statistic" in source_norm:
        return "legacy_stat_snapshot"
    if source_norm.startswith("dsp-dataservice:"):
        return "legacy_adapter"
    return "runtime_projection"


def summary_with_source_kind(value: dict[str, Any] | None, source_ref: Any) -> dict[str, Any]:
    summary = safe_json(value)
    if not isinstance(summary, dict):
        summary = {}
    return summary | {"source_kind": adapter_source_kind(source_ref)}


def legacy_mapping_payload(payload: dict[str, Any], *, tenant_id: str = "sd-default") -> dict[str, Any]:
    source_ref = str(payload["source_ref"])
    source_parts = source_ref.split(":")
    legacy_system = source_parts[0] if source_parts and source_parts[0] else str(payload.get("legacy_system", "dsp-dataservice"))
    legacy_object_type = str(payload.get("legacy_object_type") or (source_parts[1] if len(source_parts) > 1 else source_ref))
    legacy_object_ref = str(payload.get("legacy_object_ref") or payload.get("source_event_ref") or (":".join(source_parts[2:]) if len(source_parts) > 2 else source_ref))
    return {
        "tenant_id": tenant_id,
        "legacy_system": legacy_system,
        "legacy_object_type": legacy_object_type,
        "legacy_object_ref": legacy_object_ref,
        "canonical_type": str(payload["canonical_type"]),
        "canonical_ref": str(payload["canonical_ref"]),
        "source_ref": source_ref,
        "mapping_status": str(payload.get("mapping_status", "mapped")),
        "evidence_json": safe_json(payload.get("evidence_json") or {}),
    }
