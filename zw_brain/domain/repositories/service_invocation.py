from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from zw_brain.domain.models import ServiceInvocationMetricProjectionRecord
from zw_brain.domain.repositories.legacy_mapping import upsert_legacy_mapping_in_session
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.sanitization import summary_with_source_kind


def _failed_count(payload: dict[str, Any], fallback: int = 0) -> int:
    return int(payload.get("failed_count", payload.get("failure_count", fallback)))


def _now() -> datetime:
    return datetime.now(UTC)


def metric_canonical_ref(
    *,
    metric_scope: str,
    resource_code: str | None,
    capability_id: str | None,
    provider_org_id: str | None,
    consumer_org_id: str | None,
    provider_region_code: str | None,
    consumer_region_code: str | None,
    bucket_granularity: str,
    time_bucket: str,
) -> str:
    return ":".join(
        [
            metric_scope,
            str(resource_code or capability_id or "aggregate"),
            str(provider_org_id or "provider-any"),
            str(consumer_org_id or "consumer-any"),
            str(provider_region_code or "provider-region-any"),
            str(consumer_region_code or "consumer-region-any"),
            bucket_granularity,
            time_bucket,
        ]
    )


class ServiceInvocationMetricRepository:
    def has_metrics(self, *, tenant_id: str = "default") -> bool:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return session.execute(
                select(ServiceInvocationMetricProjectionRecord.id)
                .where(ServiceInvocationMetricProjectionRecord.tenant_id == tenant_id)
                .limit(1)
            ).scalar_one_or_none() is not None

    def list_metrics(
        self,
        *,
        tenant_id: str = "default",
        resource_code: str | None = None,
        capability_id: str | None = None,
        metric_scope: str | None = None,
    ) -> list[ServiceInvocationMetricProjectionRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            statement = select(ServiceInvocationMetricProjectionRecord).where(
                ServiceInvocationMetricProjectionRecord.tenant_id == tenant_id
            )
            if resource_code:
                statement = statement.where(ServiceInvocationMetricProjectionRecord.resource_code == resource_code)
            if capability_id:
                statement = statement.where(ServiceInvocationMetricProjectionRecord.capability_id == capability_id)
            if metric_scope:
                statement = statement.where(ServiceInvocationMetricProjectionRecord.metric_scope == metric_scope)
            return list(session.execute(statement.order_by(ServiceInvocationMetricProjectionRecord.time_bucket)).scalars())

    def upsert_metric(self, payload: dict[str, Any], *, tenant_id: str = "default") -> ServiceInvocationMetricProjectionRecord:
        SessionLocal = create_session_factory()
        now = _now()
        metric_scope = str(payload.get("metric_scope", "resource"))
        resource_code = payload.get("resource_code")
        capability_id = payload.get("capability_id")
        provider_org_id = payload.get("provider_org_id")
        consumer_org_id = payload.get("consumer_org_id")
        provider_region_code = payload.get("provider_region_code")
        consumer_region_code = payload.get("consumer_region_code") or payload.get("consumer_region")
        bucket_granularity = str(payload.get("bucket_granularity", "day"))
        time_bucket = str(payload["time_bucket"])
        with SessionLocal() as session:
            record = session.execute(
                select(ServiceInvocationMetricProjectionRecord).where(
                    ServiceInvocationMetricProjectionRecord.tenant_id == tenant_id,
                    ServiceInvocationMetricProjectionRecord.metric_scope == metric_scope,
                    ServiceInvocationMetricProjectionRecord.resource_code == resource_code,
                    ServiceInvocationMetricProjectionRecord.capability_id == capability_id,
                    ServiceInvocationMetricProjectionRecord.provider_org_id == provider_org_id,
                    ServiceInvocationMetricProjectionRecord.consumer_org_id == consumer_org_id,
                    ServiceInvocationMetricProjectionRecord.provider_region_code == provider_region_code,
                    ServiceInvocationMetricProjectionRecord.consumer_region_code == consumer_region_code,
                    ServiceInvocationMetricProjectionRecord.bucket_granularity == bucket_granularity,
                    ServiceInvocationMetricProjectionRecord.time_bucket == time_bucket,
                )
            ).scalar_one_or_none()
            summary_json = summary_with_source_kind(payload.get("summary_json"), payload.get("source_event_ref"))
            if record is None:
                record = ServiceInvocationMetricProjectionRecord(
                    tenant_id=tenant_id,
                    metric_scope=metric_scope,
                    resource_code=resource_code,
                    capability_id=capability_id,
                    provider_org_id=provider_org_id,
                    consumer_org_id=consumer_org_id,
                    provider_region_code=provider_region_code,
                    consumer_region_code=consumer_region_code,
                    consumer_region=consumer_region_code,
                    consumer_app_ref=payload.get("consumer_app_ref"),
                    bucket_granularity=bucket_granularity,
                    time_bucket=time_bucket,
                    invoke_count=int(payload.get("invoke_count", 0)),
                    success_count=int(payload.get("success_count", 0)),
                    failed_count=_failed_count(payload),
                    provider_error_count=int(payload.get("provider_error_count", 0)),
                    consumer_error_count=int(payload.get("consumer_error_count", 0)),
                    gateway_error_count=int(payload.get("gateway_error_count", 0)),
                    other_error_count=int(payload.get("other_error_count", 0)),
                    error_count=int(payload.get("error_count", 0)),
                    apply_count=int(payload.get("apply_count", 0)),
                    avg_latency_ms=payload.get("avg_latency_ms"),
                    p95_latency_ms=payload.get("p95_latency_ms"),
                    last_error_code=payload.get("last_error_code"),
                    last_error_at=payload.get("last_error_at"),
                    source_event_ref=payload.get("source_event_ref"),
                    summary_json=summary_json,
                    generated_at=now,
                )
                session.add(record)
            else:
                record.provider_region_code = payload.get("provider_region_code", record.provider_region_code)
                record.consumer_region_code = consumer_region_code or record.consumer_region_code
                record.consumer_region = consumer_region_code or record.consumer_region
                record.consumer_app_ref = payload.get("consumer_app_ref", record.consumer_app_ref)
                record.invoke_count = int(payload.get("invoke_count", record.invoke_count))
                record.success_count = int(payload.get("success_count", record.success_count))
                record.failed_count = _failed_count(payload, record.failed_count)
                record.provider_error_count = int(payload.get("provider_error_count", record.provider_error_count))
                record.consumer_error_count = int(payload.get("consumer_error_count", record.consumer_error_count))
                record.gateway_error_count = int(payload.get("gateway_error_count", record.gateway_error_count))
                record.other_error_count = int(payload.get("other_error_count", record.other_error_count))
                record.error_count = int(payload.get("error_count", record.error_count))
                record.apply_count = int(payload.get("apply_count", record.apply_count))
                record.avg_latency_ms = payload.get("avg_latency_ms", record.avg_latency_ms)
                record.p95_latency_ms = payload.get("p95_latency_ms", record.p95_latency_ms)
                record.last_error_code = payload.get("last_error_code", record.last_error_code)
                record.last_error_at = payload.get("last_error_at", record.last_error_at)
                record.source_event_ref = payload.get("source_event_ref", record.source_event_ref)
                record.summary_json = summary_json or record.summary_json
                record.generated_at = now
            canonical_ref = metric_canonical_ref(
                metric_scope=metric_scope,
                resource_code=resource_code,
                capability_id=capability_id,
                provider_org_id=provider_org_id,
                consumer_org_id=consumer_org_id,
                provider_region_code=provider_region_code,
                consumer_region_code=consumer_region_code,
                bucket_granularity=bucket_granularity,
                time_bucket=time_bucket,
            )
            upsert_legacy_mapping_in_session(
                session,
                {
                    "source_ref": record.source_event_ref,
                    "legacy_object_ref": payload.get("legacy_object_ref") or canonical_ref,
                    "canonical_type": "service_invocation_metric_projection",
                    "canonical_ref": canonical_ref,
                    "evidence_json": {"invoke_count": record.invoke_count, "failed_count": record.failed_count},
                },
                tenant_id=tenant_id,
            )
            session.commit()
            session.refresh(record)
            return record
