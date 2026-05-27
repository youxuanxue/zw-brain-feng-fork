"""Delivery serializers — attempt / evidence / exchange_metric.

Extracted from ``BrainService._<name>_record_to_dict`` (Phase 1.1).
"""
from __future__ import annotations

import copy
from typing import Any


def delivery_attempt_to_dict(record: Any) -> dict[str, Any]:
    return {
        "attempt_code": record.attempt_code,
        "delivery_code": record.delivery_code,
        "subscription_code": record.subscription_code,
        "attempt_kind": record.attempt_kind,
        "state": record.state,
        "executor_ref": record.executor_ref,
        "evidence_ref": record.evidence_ref,
        "payload_json": copy.deepcopy(record.payload_json),
    }


def delivery_evidence_to_dict(record: Any) -> dict[str, Any]:
    return {
        "evidence_ref": record.evidence_ref,
        "delivery_code": record.delivery_code,
        "attempt_code": record.attempt_code,
        "executor_kind": record.executor_kind,
        "executor_ref": record.executor_ref,
        "evidence_kind": record.evidence_kind,
        "result_status": record.result_status,
        "sanitized_payload_json": copy.deepcopy(record.sanitized_payload_json),
    }


def exchange_metric_to_dict(record: Any) -> dict[str, Any]:
    return {
        "metric_scope": record.metric_scope,
        "resource_code": record.resource_code,
        "delivery_code": record.delivery_code,
        "subscription_code": record.subscription_code,
        "provider_org_id": record.provider_org_id,
        "consumer_org_id": record.consumer_org_id,
        "bucket_granularity": record.bucket_granularity,
        "time_bucket": record.time_bucket,
        "exchange_count": record.exchange_count,
        "success_count": record.success_count,
        "failed_count": record.failed_count,
        "record_count": record.record_count,
        "file_count": record.file_count,
        "table_count": record.table_count,
        "last_error_code": record.last_error_code,
        "summary_json": copy.deepcopy(record.summary_json),
    }
