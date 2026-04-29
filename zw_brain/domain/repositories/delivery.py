from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select

from zw_brain.domain.models import DeliveryReceiptRecord, DeliveryTaskRecord
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.sanitization import safe_json


class DeliveryRepository:
    def list_tasks(self) -> list[DeliveryTaskRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(session.execute(select(DeliveryTaskRecord).order_by(DeliveryTaskRecord.delivery_code)).scalars())

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

    def upsert_from_delivery(self, delivery: dict[str, Any], *, tenant_id: str = "default") -> None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(select(DeliveryTaskRecord).where(DeliveryTaskRecord.delivery_code == delivery["id"])).scalar_one_or_none()
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

            session.execute(delete(DeliveryReceiptRecord).where(DeliveryReceiptRecord.delivery_code == delivery["id"]))
            session.add(
                DeliveryReceiptRecord(
                    delivery_code=delivery["id"],
                    receipt_type=self._receipt_type(delivery),
                    receipt_no=delivery.get("receiptNo") or delivery.get("backflow", {}).get("candidateObject"),
                    receipt_status=self._receipt_status(delivery),
                    payload_json=safe_json(
                        {
                            "note": delivery.get("note"),
                            "backflow": delivery.get("backflow", {}),
                            "history": delivery.get("history", []),
                        }
                    ),
                )
            )
            session.commit()

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
