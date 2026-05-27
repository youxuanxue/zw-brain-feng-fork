"""Adapter serializers — adapter_run / external_mapping.

Extracted from ``BrainService._<name>_record_to_dict`` (Phase 1.1).
"""
from __future__ import annotations

import copy
from typing import Any


def adapter_run_to_dict(item: Any) -> dict[str, Any]:
    return {
        "id": item.id,
        "adapter_slug": item.adapter_slug,
        "operation": item.operation,
        "direction": item.direction,
        "source_ref": item.source_ref,
        "idempotency_key": item.idempotency_key,
        "status": item.status,
        "target_count": item.target_count,
        "success_count": item.success_count,
        "failure_count": item.failure_count,
        "receipt_json": copy.deepcopy(item.receipt_json),
        "error_summary": item.error_summary,
    }


def external_mapping_to_dict(item: Any) -> dict[str, Any]:
    return {
        "id": item.id,
        "external_system": item.external_system,
        "direction": item.direction,
        "local_aggregate_type": item.local_aggregate_type,
        "local_aggregate_id": item.local_aggregate_id,
        "external_object_type": item.external_object_type,
        "external_object_id": item.external_object_id,
        "protocol_version": item.protocol_version,
        "batch_no": item.batch_no,
        "status": item.status,
        "last_receipt_json": copy.deepcopy(item.last_receipt_json),
    }
