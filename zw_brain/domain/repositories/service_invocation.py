from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from zw_brain.domain.models import LegacyObjectMappingRecord, ServiceInvocationMetricProjectionRecord
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.sanitization import adapter_source_kind, legacy_mapping_payload, safe_json


def _now() -> datetime:
    return datetime.now(UTC)


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
                    ServiceInvocationMetricProjectionRecord.time_bucket == time_bucket,
                )
            ).scalar_one_or_none()
            summary_json = safe_json(payload.get("summary_json") or {}) | {"source_kind": adapter_source_kind(payload.get("source_event_ref"))}
            if record is None:
                record = ServiceInvocationMetricProjectionRecord(
                    tenant_id=tenant_id,
                    metric_scope=metric_scope,
                    resource_code=resource_code,
                    capability_id=capability_id,
                    provider_org_id=provider_org_id,
                    consumer_org_id=consumer_org_id,
                    consumer_region=payload.get("consumer_region"),
                    consumer_app_ref=payload.get("consumer_app_ref"),
                    time_bucket=time_bucket,
                    invoke_count=int(payload.get("invoke_count", 0)),
                    success_count=int(payload.get("success_count", 0)),
                    failure_count=int(payload.get("failure_count", 0)),
                    error_count=int(payload.get("error_count", 0)),
                    avg_latency_ms=payload.get("avg_latency_ms"),
                    source_event_ref=payload.get("source_event_ref"),
                    summary_json=summary_json,
                    generated_at=now,
                )
                session.add(record)
            else:
                record.consumer_region = payload.get("consumer_region", record.consumer_region)
                record.consumer_app_ref = payload.get("consumer_app_ref", record.consumer_app_ref)
                record.invoke_count = int(payload.get("invoke_count", record.invoke_count))
                record.success_count = int(payload.get("success_count", record.success_count))
                record.failure_count = int(payload.get("failure_count", record.failure_count))
                record.error_count = int(payload.get("error_count", record.error_count))
                record.avg_latency_ms = payload.get("avg_latency_ms", record.avg_latency_ms)
                record.source_event_ref = payload.get("source_event_ref", record.source_event_ref)
                record.summary_json = summary_json or record.summary_json
                record.generated_at = now
            canonical_ref = ":".join(
                [
                    metric_scope,
                    str(resource_code or capability_id or "aggregate"),
                    str(provider_org_id or "provider-any"),
                    str(consumer_org_id or "consumer-any"),
                    time_bucket,
                ]
            )
            self._upsert_legacy_mapping(
                session,
                {
                    "source_ref": record.source_event_ref,
                    "legacy_object_ref": payload.get("legacy_object_ref") or canonical_ref,
                    "canonical_type": "service_invocation_metric_projection",
                    "canonical_ref": canonical_ref,
                    "evidence_json": {"invoke_count": record.invoke_count, "failure_count": record.failure_count},
                },
                tenant_id=tenant_id,
            )
            session.commit()
            session.refresh(record)
            return record

    def _upsert_legacy_mapping(self, session: Any, payload: dict[str, Any], *, tenant_id: str) -> None:
        if not payload.get("source_ref"):
            return
        mapping = legacy_mapping_payload(payload, tenant_id=tenant_id)
        record = session.execute(
            select(LegacyObjectMappingRecord).where(
                LegacyObjectMappingRecord.tenant_id == tenant_id,
                LegacyObjectMappingRecord.legacy_system == mapping["legacy_system"],
                LegacyObjectMappingRecord.legacy_object_type == mapping["legacy_object_type"],
                LegacyObjectMappingRecord.legacy_object_ref == mapping["legacy_object_ref"],
                LegacyObjectMappingRecord.canonical_type == mapping["canonical_type"],
                LegacyObjectMappingRecord.canonical_ref == mapping["canonical_ref"],
            )
        ).scalar_one_or_none()
        if record is None:
            session.add(LegacyObjectMappingRecord(**mapping))
        else:
            record.source_ref = mapping["source_ref"]
            record.evidence_json = mapping["evidence_json"]
