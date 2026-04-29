from __future__ import annotations

import copy
from typing import Any

SENSITIVE_JSON_KEYS = {"secret", "password", "token", "credential", "app_secret", "superior_app_secret"}


def safe_json(value: dict[str, Any] | None) -> dict[str, Any]:
    if not value:
        return {}
    return {key: item for key, item in copy.deepcopy(value).items() if key.lower() not in SENSITIVE_JSON_KEYS}


def adapter_source_kind(source_ref: Any) -> str:
    source = str(source_ref or "")
    if "audit" in source or "capability_call" in source:
        return "audit_event"
    if "gateway_log" in source or "gateway-log" in source or "/openapi/report" in source or "GATEWAY_REPORT" in source:
        return "gateway_adapter"
    if "api_service_times" in source or "api_service_statistic" in source:
        return "legacy_stat_snapshot"
    if source.startswith("dsp-dataservice:"):
        return "legacy_adapter"
    return "runtime_projection"


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
        "evidence_json": safe_json(payload.get("evidence_json") or {}),
    }
