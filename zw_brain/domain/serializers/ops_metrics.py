"""Ops / metrics serializers — gateway_runtime / service_metric.

Extracted from ``BrainService._<name>_record_to_dict`` (Phase 1.1).
Action H commit 2: ``metric_summary`` / ``exchange_metric_summary`` aggregate
helpers moved here from BrainService — pure data-shape transforms with no
domain context (called by b1/ops_service.py + b1/exchange_statistics_query.py).
"""
from __future__ import annotations

import copy
from typing import Any


def metric_summary(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate service_invocation metrics into invoke/success/failed/error totals."""
    return {
        "invokeCount": sum(int(item.get("invoke_count", 0)) for item in metrics),
        "successCount": sum(int(item.get("success_count", 0)) for item in metrics),
        "failedCount": sum(int(item.get("failed_count", item.get("failure_count", 0))) for item in metrics),
        "errorCount": sum(int(item.get("error_count", 0)) for item in metrics),
    }


def exchange_metric_summary(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate exchange_metric rows into exchange/success/failed/record totals."""
    return {
        "exchangeCount": sum(int(item.get("exchange_count", 0)) for item in metrics),
        "successCount": sum(int(item.get("success_count", 0)) for item in metrics),
        "failedCount": sum(int(item.get("failed_count", 0)) for item in metrics),
        "recordCount": sum(int(item.get("record_count", 0)) for item in metrics),
    }


def gateway_to_dict(record: Any) -> dict[str, Any]:
    return {
        "gateway_instance_id": record.gateway_instance_id,
        "runtime_profile": record.runtime_profile,
        "status": record.status,
        "last_reported_at": record.last_reported_at.isoformat(),
        "source_ref": record.source_ref,
        "summary_json": copy.deepcopy(record.summary_json),
        "generated_at": record.generated_at.isoformat(),
    }


def metric_to_dict(record: Any) -> dict[str, Any]:
    return {
        "metric_scope": record.metric_scope,
        "resource_code": record.resource_code,
        "capability_id": record.capability_id,
        "provider_org_id": record.provider_org_id,
        "consumer_org_id": record.consumer_org_id,
        "provider_region_code": record.provider_region_code,
        "consumer_region_code": record.consumer_region_code,
        "consumer_region": record.consumer_region,
        "consumer_app_ref": record.consumer_app_ref,
        "bucket_granularity": record.bucket_granularity,
        "time_bucket": record.time_bucket,
        "invoke_count": record.invoke_count,
        "success_count": record.success_count,
        "failed_count": record.failed_count,
        "provider_error_count": record.provider_error_count,
        "consumer_error_count": record.consumer_error_count,
        "gateway_error_count": record.gateway_error_count,
        "other_error_count": record.other_error_count,
        "error_count": record.error_count,
        "apply_count": record.apply_count,
        "avg_latency_ms": record.avg_latency_ms,
        "p95_latency_ms": record.p95_latency_ms,
        "last_error_code": record.last_error_code,
        "last_error_at": record.last_error_at.isoformat() if record.last_error_at else None,
        "source_event_ref": record.source_event_ref,
        "summary_json": copy.deepcopy(record.summary_json),
    }
