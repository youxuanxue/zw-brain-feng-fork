from __future__ import annotations

import copy
from typing import Any

SENSITIVE_JSON_KEYS = {
    "secret",
    "password",
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
    "session_key",
    "secret_key",
    "certificate",
    "cert",
    "private_key",
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


def legacy_mapping_payload(payload: dict[str, Any], *, tenant_id: str = "default") -> dict[str, Any]:
    source_ref = str(payload["source_ref"])
    legacy_system, _, legacy_object_type = source_ref.partition(":")
    if not legacy_system or not legacy_object_type:
        legacy_system = str(payload.get("legacy_system", "dsp-dataservice"))
        legacy_object_type = str(payload.get("legacy_object_type", source_ref))
    legacy_object_ref = str(payload.get("legacy_object_ref") or payload.get("source_event_ref") or source_ref)
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
