from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select

from zw_brain.domain.models import (
    DeliveryAttemptRecord,
    DeliveryExecutionEvidenceRecord,
    DeliveryReceiptRecord,
    DeliverySubscriptionRecord,
    DeliveryTaskRecord,
    ExchangeMetricProjectionRecord,
)
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.sanitization import safe_json


def _now() -> datetime:
    return datetime.now(UTC)


class DeliveryRepository:
    def list_tasks(self, *, tenant_id: str = "sd-default") -> list[DeliveryTaskRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(
                session.execute(
                    select(DeliveryTaskRecord)
                    .where(DeliveryTaskRecord.tenant_id == tenant_id)
                    .order_by(DeliveryTaskRecord.delivery_code)
                ).scalars()
            )

    def list_receipts(self, delivery_code: str) -> list[DeliveryReceiptRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(
                session.execute(
                    select(DeliveryReceiptRecord)
                    .where(DeliveryReceiptRecord.delivery_code == delivery_code)
                    .order_by(DeliveryReceiptRecord.issued_at)
                ).scalars()
            )

    def list_subscriptions(self, delivery_code: str | None = None, *, tenant_id: str = "sd-default") -> list[DeliverySubscriptionRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            statement = select(DeliverySubscriptionRecord).where(DeliverySubscriptionRecord.tenant_id == tenant_id)
            if delivery_code:
                statement = statement.where(DeliverySubscriptionRecord.delivery_code == delivery_code)
            return list(session.execute(statement.order_by(DeliverySubscriptionRecord.updated_at)).scalars())

    def list_attempts(self, delivery_code: str | None = None, attempt_code: str | None = None, *, tenant_id: str = "sd-default") -> list[DeliveryAttemptRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            statement = select(DeliveryAttemptRecord).where(DeliveryAttemptRecord.tenant_id == tenant_id)
            if delivery_code:
                statement = statement.where(DeliveryAttemptRecord.delivery_code == delivery_code)
            if attempt_code:
                statement = statement.where(DeliveryAttemptRecord.attempt_code == attempt_code)
            return list(session.execute(statement.order_by(DeliveryAttemptRecord.updated_at)).scalars())

    def list_execution_evidence(self, delivery_code: str | None = None, attempt_code: str | None = None, *, tenant_id: str = "sd-default") -> list[DeliveryExecutionEvidenceRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            statement = select(DeliveryExecutionEvidenceRecord).where(DeliveryExecutionEvidenceRecord.tenant_id == tenant_id)
            if delivery_code:
                statement = statement.where(DeliveryExecutionEvidenceRecord.delivery_code == delivery_code)
            if attempt_code:
                statement = statement.where(DeliveryExecutionEvidenceRecord.attempt_code == attempt_code)
            return list(session.execute(statement.order_by(DeliveryExecutionEvidenceRecord.captured_at)).scalars())

    def list_exchange_metrics(
        self,
        *,
        metric_scope: str | None = None,
        resource_code: str | None = None,
        delivery_code: str | None = None,
        tenant_id: str = "sd-default",
    ) -> list[ExchangeMetricProjectionRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            statement = select(ExchangeMetricProjectionRecord).where(ExchangeMetricProjectionRecord.tenant_id == tenant_id)
            if metric_scope:
                statement = statement.where(ExchangeMetricProjectionRecord.metric_scope == metric_scope)
            if resource_code:
                statement = statement.where(ExchangeMetricProjectionRecord.resource_code == resource_code)
            if delivery_code:
                statement = statement.where(ExchangeMetricProjectionRecord.delivery_code == delivery_code)
            return list(session.execute(statement.order_by(ExchangeMetricProjectionRecord.generated_at)).scalars())

    def upsert_subscription(self, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> DeliverySubscriptionRecord:
        subscription_code = str(payload.get("subscription_code") or payload.get("subscription_id") or f"SUB-{payload['delivery_code']}")
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(
                select(DeliverySubscriptionRecord).where(
                    DeliverySubscriptionRecord.tenant_id == tenant_id,
                    DeliverySubscriptionRecord.subscription_code == subscription_code,
                )
            ).scalar_one_or_none()
            if record is None:
                record = DeliverySubscriptionRecord(
                    tenant_id=tenant_id,
                    subscription_code=subscription_code,
                    delivery_code=str(payload["delivery_code"]),
                    resource_code=payload.get("resource_code"),
                    status=str(payload.get("status", "active")),
                    schedule_ref_json=safe_json(payload.get("schedule_ref_json") or payload.get("schedule_ref") or {}),
                    policy_snapshot_json=safe_json(payload.get("policy_snapshot_json") or payload.get("policy_snapshot") or {}),
                    legacy_status_snapshot_json=safe_json(payload.get("legacy_status_snapshot_json") or payload.get("legacy_status_snapshot") or {}),
                )
                session.add(record)
            else:
                record.delivery_code = str(payload["delivery_code"])
                record.resource_code = payload.get("resource_code", record.resource_code)
                record.status = str(payload.get("status", record.status))
                record.schedule_ref_json = safe_json(payload.get("schedule_ref_json") or payload.get("schedule_ref") or record.schedule_ref_json)
                record.policy_snapshot_json = safe_json(payload.get("policy_snapshot_json") or payload.get("policy_snapshot") or record.policy_snapshot_json)
                record.legacy_status_snapshot_json = safe_json(payload.get("legacy_status_snapshot_json") or payload.get("legacy_status_snapshot") or record.legacy_status_snapshot_json)
                record.updated_at = _now()
            session.commit()
            session.refresh(record)
            return record

    def upsert_attempt(self, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> DeliveryAttemptRecord:
        attempt_code = str(payload.get("attempt_code") or payload.get("attempt_id") or f"ATT-{payload['delivery_code']}-{payload.get('attempt_kind', 'exchange')}")
        started_at = payload.get("started_at")
        finished_at = payload.get("finished_at")
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(
                select(DeliveryAttemptRecord).where(
                    DeliveryAttemptRecord.tenant_id == tenant_id,
                    DeliveryAttemptRecord.attempt_code == attempt_code,
                )
            ).scalar_one_or_none()
            if record is None:
                record = DeliveryAttemptRecord(
                    tenant_id=tenant_id,
                    attempt_code=attempt_code,
                    delivery_code=str(payload["delivery_code"]),
                    subscription_code=payload.get("subscription_code") or payload.get("subscription_id"),
                    attempt_kind=str(payload.get("attempt_kind", "exchange")),
                    state=str(payload.get("state", "planned")),
                    executor_ref=payload.get("executor_ref"),
                    evidence_ref=payload.get("evidence_ref"),
                    payload_json=safe_json(payload.get("payload_json") or payload),
                    started_at=started_at,
                    finished_at=finished_at,
                )
                session.add(record)
            else:
                record.delivery_code = str(payload["delivery_code"])
                record.subscription_code = payload.get("subscription_code") or payload.get("subscription_id") or record.subscription_code
                record.attempt_kind = str(payload.get("attempt_kind", record.attempt_kind))
                record.state = str(payload.get("state", record.state))
                record.executor_ref = payload.get("executor_ref", record.executor_ref)
                record.evidence_ref = payload.get("evidence_ref", record.evidence_ref)
                record.payload_json = safe_json(payload.get("payload_json") or payload)
                record.started_at = started_at or record.started_at
                record.finished_at = finished_at or record.finished_at
                record.updated_at = _now()
            session.commit()
            session.refresh(record)
            return record

    def add_execution_evidence(self, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> DeliveryExecutionEvidenceRecord:
        evidence_ref = str(payload.get("evidence_ref") or payload.get("evidence_id") or f"EVD-{payload.get('attempt_code') or payload.get('delivery_code')}")
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(
                select(DeliveryExecutionEvidenceRecord).where(
                    DeliveryExecutionEvidenceRecord.tenant_id == tenant_id,
                    DeliveryExecutionEvidenceRecord.evidence_ref == evidence_ref,
                )
            ).scalar_one_or_none()
            values = {
                "tenant_id": tenant_id,
                "evidence_ref": evidence_ref,
                "delivery_code": payload.get("delivery_code"),
                "attempt_code": payload.get("attempt_code") or payload.get("attempt_id"),
                "executor_kind": str(payload.get("executor_kind", "builtin")),
                "executor_ref": payload.get("executor_ref"),
                "evidence_kind": str(payload.get("evidence_kind", "execution_receipt")),
                "result_status": str(payload.get("result_status", payload.get("state", "succeeded"))),
                "sanitized_payload_json": safe_json(payload.get("sanitized_payload_json") or payload.get("payload_json") or payload),
                "captured_at": payload.get("captured_at") or _now(),
            }
            if record is None:
                record = DeliveryExecutionEvidenceRecord(**values)
                session.add(record)
            else:
                record.delivery_code = values["delivery_code"]
                record.attempt_code = values["attempt_code"]
                record.executor_kind = values["executor_kind"]
                record.executor_ref = values["executor_ref"]
                record.evidence_kind = values["evidence_kind"]
                record.result_status = values["result_status"]
                record.sanitized_payload_json = values["sanitized_payload_json"]
                record.captured_at = values["captured_at"]
            session.commit()
            session.refresh(record)
            return record

    def upsert_exchange_metric(self, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> ExchangeMetricProjectionRecord:
        values = {
            "tenant_id": tenant_id,
            "metric_scope": str(payload.get("metric_scope", "delivery")),
            "resource_code": payload.get("resource_code"),
            "delivery_code": payload.get("delivery_code"),
            "subscription_code": payload.get("subscription_code") or payload.get("subscription_id"),
            "provider_org_id": payload.get("provider_org_id"),
            "consumer_org_id": payload.get("consumer_org_id"),
            "bucket_granularity": str(payload.get("bucket_granularity", "event")),
            "time_bucket": str(payload.get("time_bucket", datetime.now(UTC).strftime("%Y-%m-%d"))),
            "exchange_count": int(payload.get("exchange_count", 1)),
            "success_count": int(payload.get("success_count", 1 if payload.get("status", "succeeded") in {"succeeded", "published", "active"} else 0)),
            "failed_count": int(payload.get("failed_count", 0)),
            "record_count": int(payload.get("record_count", 0)),
            "file_count": int(payload.get("file_count", 0)),
            "table_count": int(payload.get("table_count", 0)),
            "last_error_code": payload.get("last_error_code"),
            "last_error_at": payload.get("last_error_at"),
            "summary_json": safe_json(payload.get("summary_json") or payload.get("metrics") or {}),
        }
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(
                select(ExchangeMetricProjectionRecord).where(
                    ExchangeMetricProjectionRecord.tenant_id == tenant_id,
                    ExchangeMetricProjectionRecord.metric_scope == values["metric_scope"],
                    ExchangeMetricProjectionRecord.resource_code == values["resource_code"],
                    ExchangeMetricProjectionRecord.delivery_code == values["delivery_code"],
                    ExchangeMetricProjectionRecord.subscription_code == values["subscription_code"],
                    ExchangeMetricProjectionRecord.provider_org_id == values["provider_org_id"],
                    ExchangeMetricProjectionRecord.consumer_org_id == values["consumer_org_id"],
                    ExchangeMetricProjectionRecord.bucket_granularity == values["bucket_granularity"],
                    ExchangeMetricProjectionRecord.time_bucket == values["time_bucket"],
                )
            ).scalar_one_or_none()
            if record is None:
                record = ExchangeMetricProjectionRecord(**values)
                session.add(record)
            else:
                record.exchange_count = values["exchange_count"]
                record.success_count = values["success_count"]
                record.failed_count = values["failed_count"]
                record.record_count = values["record_count"]
                record.file_count = values["file_count"]
                record.table_count = values["table_count"]
                record.last_error_code = values["last_error_code"]
                record.last_error_at = values["last_error_at"]
                record.summary_json = values["summary_json"]
                record.generated_at = _now()
            session.commit()
            session.refresh(record)
            return record

    def append_receipt(self, payload: dict[str, Any]) -> DeliveryReceiptRecord:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            acknowledged_at = _now() if payload.get("acknowledged", True) else None
            record = DeliveryReceiptRecord(
                delivery_code=str(payload["delivery_code"]),
                receipt_type=str(payload.get("receipt_type", "exchange")),
                receipt_no=payload.get("receipt_no"),
                receipt_status=str(payload.get("receipt_status", "issued")),
                payload_json=safe_json(payload.get("payload_json") or payload.get("receipt") or {}),
                acknowledged_at=acknowledged_at,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def upsert_from_delivery(self, delivery: dict[str, Any], *, tenant_id: str = "sd-default") -> None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(
                select(DeliveryTaskRecord).where(
                    DeliveryTaskRecord.tenant_id == tenant_id,
                    DeliveryTaskRecord.delivery_code == delivery["id"],
                )
            ).scalar_one_or_none()
            if record is None:
                record = DeliveryTaskRecord(
                    tenant_id=tenant_id,
                    delivery_code=delivery["id"],
                    application_code=delivery["requestId"],
                    state=delivery["status"],
                    channel=delivery["channel"],
                    payload_json=self._payload(delivery),
                )
                session.add(record)
            else:
                record.application_code = delivery["requestId"]
                record.state = delivery["status"]
                record.channel = delivery["channel"]
                record.payload_json = self._payload(delivery)

            receipt_no = delivery.get("receiptNo") or delivery.get("backflow", {}).get("candidateObject")
            receipt_payload = safe_json(
                {
                    "note": delivery.get("note"),
                    "backflow": delivery.get("backflow", {}),
                    "history": delivery.get("history", []),
                }
            )
            existing_receipt = session.execute(
                select(DeliveryReceiptRecord).where(
                    DeliveryReceiptRecord.delivery_code == delivery["id"],
                    DeliveryReceiptRecord.receipt_no == receipt_no,
                )
            ).scalar_one_or_none()
            if existing_receipt is None:
                session.add(
                    DeliveryReceiptRecord(
                        delivery_code=delivery["id"],
                        receipt_type=self._receipt_type(delivery),
                        receipt_no=receipt_no,
                        receipt_status=self._receipt_status(delivery),
                        payload_json=receipt_payload,
                    )
                )
            else:
                if self._is_delivery_projection_receipt(existing_receipt):
                    receipt_status = self._receipt_status(delivery)
                    existing_receipt.receipt_type = self._receipt_type(delivery)
                    existing_receipt.receipt_status = receipt_status
                    existing_receipt.payload_json = receipt_payload
                    existing_receipt.acknowledged_at = _now() if receipt_status in {"acknowledged", "reconciled"} else existing_receipt.acknowledged_at
            session.commit()

    def _is_delivery_projection_receipt(self, receipt: DeliveryReceiptRecord) -> bool:
        payload = receipt.payload_json if isinstance(receipt.payload_json, dict) else {}
        return bool({"note", "backflow", "history"} & set(payload))

    def _payload(self, delivery: dict[str, Any]) -> dict[str, Any]:
        payload = safe_json(delivery)
        if not isinstance(payload, dict):
            return {}
        access = delivery.get("access")
        if isinstance(access, dict):
            payload["access_grant_snapshot"] = safe_json(
                {
                    "resource_code": access.get("resource_code") or delivery.get("resourceId") or delivery.get("resource_code"),
                    "application_code": delivery.get("requestId"),
                    "grant_ref": access.get("grant_ref") or access.get("auth_ref"),
                    "policy_ref": access.get("policy_ref"),
                    "status": delivery.get("status"),
                }
            )
        return payload

    def _receipt_type(self, delivery: dict[str, Any]) -> str:
        if delivery.get("backflow", {}).get("candidateObject") and delivery["channel"] == "预填下发 + 汇总回流":
            return "subscription_ack"
        if delivery["channel"] == "准入拦截":
            return "exchange"
        if delivery["channel"] == "内部修复":
            return "national_ack"
        return "provision"

    def _receipt_status(self, delivery: dict[str, Any]) -> str:
        if delivery.get("receiptStatus") == "reconciled":
            return "reconciled"
        backflow_status = delivery.get("backflow", {}).get("status")
        if backflow_status == "已确认":
            return "acknowledged"
        if delivery["status"] == "failed":
            return "rejected"
        if delivery["status"] == "completed":
            return "issued"
        return "issued"
