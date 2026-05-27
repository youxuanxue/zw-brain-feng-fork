"""Metadata serializers — schema_snapshot / schema_mapping (+ helpers) /
gather_evidence / lineage.

Extracted from ``BrainService._<name>_record_to_dict`` and the 3 schema-mapping
helpers (Phase 1.1).

The helpers are module-level publics because brain.py's ``_mapping_diagnostics``
still calls ``mask_schema_mapping_payload`` directly (it operates on catalog
items, not mapping records).
"""
from __future__ import annotations

import copy
from typing import Any

from zw_brain.command.serializers._common import DEFAULT_MASK_ROLE
from zw_brain.shared.sensitive_mask import apply_field_masks


def schema_snapshot_to_dict(record: Any) -> dict[str, Any]:
    return {
        "snapshot_ref": record.snapshot_ref,
        "resource_code": record.resource_code,
        "binding_code": record.binding_code,
        "schema_json": copy.deepcopy(record.schema_json),
        "source_ref": record.source_ref,
        "schema_hash": record.schema_hash,
        "captured_at": record.captured_at.isoformat(),
    }


def schema_mapping_source_column(source_schema_ref: Any) -> Any:
    if not isinstance(source_schema_ref, dict):
        return None
    return (
        source_schema_ref.get("column")
        or source_schema_ref.get("table_column_id")
        or source_schema_ref.get("field")
    )


def mask_schema_mapping_payload(value: Any) -> Any:
    return apply_field_masks(
        value,
        role=DEFAULT_MASK_ROLE,
        field_policy={"address": "", "column": "", "table_column_id": "", "field": ""},
    )


def schema_mapping_diagnosis(record: Any) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    if record.status != "active":
        issues.append({"stage": "status", "reason": "inactive_mapping", "detail": f"mapping status is {record.status}"})
    if not schema_mapping_source_column(record.source_schema_ref):
        issues.append({"stage": "source_field", "reason": "missing_source_schema_ref", "detail": "source_schema_ref has no column/table_column_id/field"})
    if not record.evidence_ref:
        issues.append({"stage": "evidence", "reason": "missing_evidence_ref", "detail": "evidence_ref is empty"})
    if record.confidence_level in {"conflicted", "low"}:
        issues.append({"stage": "confidence", "reason": "mapping_conflict", "detail": f"confidence_level is {record.confidence_level}"})
    return {
        "ok": not issues,
        "stage": "ready" if not issues else issues[0]["stage"],
        "reason": None if not issues else issues[0]["reason"],
        "issues": issues,
    }


def schema_mapping_to_dict(record: Any) -> dict[str, Any]:
    source_schema_ref = mask_schema_mapping_payload(copy.deepcopy(record.source_schema_ref))
    if not isinstance(source_schema_ref, dict):
        source_schema_ref = {"value": source_schema_ref} if source_schema_ref else {}
    mapping_rule_json = mask_schema_mapping_payload(copy.deepcopy(record.mapping_rule_json))
    if not isinstance(mapping_rule_json, dict):
        mapping_rule_json = {"value": mapping_rule_json} if mapping_rule_json else {}
    source_column = schema_mapping_source_column(source_schema_ref)
    diagnosis = schema_mapping_diagnosis(record)
    replay_steps = [
        {"step": "catalog_item", "ref": record.catalog_item_code, "status": "resolved", "detail": f"目录项 {record.catalog_item_code}"},
        {"step": "resource_binding", "ref": record.binding_code, "status": "resolved", "detail": f"资源 {record.resource_code} / 通道 {record.binding_code}"},
        {"step": "source_field", "ref": source_column, "status": "resolved" if source_column else "missing", "detail": source_schema_ref},
        {"step": "evidence", "ref": record.evidence_ref, "status": "resolved" if record.evidence_ref else "missing", "detail": "legacy/import evidence ref"},
    ]
    return {
        "mapping_code": record.mapping_code,
        "catalog_code": record.catalog_code,
        "catalog_item_code": record.catalog_item_code,
        "resource_code": record.resource_code,
        "binding_code": record.binding_code,
        "source_schema_ref": source_schema_ref,
        "mapping_rule_json": mapping_rule_json,
        "confidence_level": record.confidence_level,
        "evidence_ref": record.evidence_ref,
        "source_ref": record.evidence_ref,
        "status": record.status,
        "confirmed_by": record.confirmed_by,
        "confirmed_at": record.confirmed_at.isoformat() if record.confirmed_at else None,
        "generated_at": record.updated_at.isoformat(),
        "explain": {
            "summary": f"目录项 {record.catalog_item_code} 通过资源 {record.resource_code} 的 {record.binding_code} 通道绑定到来源字段。",
            "source_column": source_column,
            "mapping_rule": mapping_rule_json or {"method": "direct"},
            "confidence": record.confidence_level,
        },
        "replay": {"mapping_code": record.mapping_code, "steps": replay_steps},
        "diagnosis": diagnosis,
    }


def gather_evidence_to_dict(record: Any) -> dict[str, Any]:
    source_ref = record.source_system_ref or record.gather_task_ref
    generated_at = record.generated_at.isoformat()
    return {
        "gather_task_ref": record.gather_task_ref,
        "resource_code": record.resource_code,
        "source_system_ref": record.source_system_ref,
        "source_ref": source_ref,
        "schema_snapshot_ref": record.schema_snapshot_ref,
        "status": record.status,
        "error_summary": record.error_summary,
        "evidence_json": copy.deepcopy(record.evidence_json),
        "started_at": record.started_at.isoformat() if hasattr(record.started_at, "isoformat") else record.started_at,
        "finished_at": record.finished_at.isoformat() if hasattr(record.finished_at, "isoformat") else record.finished_at,
        "generated_at": generated_at,
        "projection_only": True,
        "evidence": {"source_ref": source_ref, "generated_at": generated_at, "projection_only": True},
    }


def lineage_to_dict(record: Any) -> dict[str, Any]:
    source_ref = record.source_evidence_ref or record.relation_ref
    generated_at = record.generated_at.isoformat()
    return {
        "relation_ref": record.relation_ref,
        "relation_scope": record.relation_scope,
        "source_resource_code": record.source_resource_code,
        "source_schema_ref": record.source_schema_ref,
        "target_resource_code": record.target_resource_code,
        "target_schema_ref": record.target_schema_ref,
        "relation_type": record.relation_type,
        "relation_rule_json": copy.deepcopy(record.relation_rule_json),
        "source_evidence_ref": record.source_evidence_ref,
        "source_ref": source_ref,
        "generated_at": generated_at,
        "projection_only": True,
        "evidence": {"source_ref": source_ref, "generated_at": generated_at, "projection_only": True},
    }
