from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, update

from zw_brain.domain.models import ApplicationRecord
from zw_brain.domain.repositories.legacy_mapping import upsert_legacy_mapping_in_session
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.sanitization import safe_json


class ApplicationRepository:
    def count_by_statuses(self, *, statuses: list[str], tenant_id: str = "sd-default") -> int:
        """Fast count for compliance metric alerts — avoids list_records +
        per-row get_resource N+1 that previously caused 30+ second queries.
        """
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return int(
                session.execute(
                    select(func.count()).select_from(ApplicationRecord)
                    .where(ApplicationRecord.tenant_id == tenant_id)
                    .where(ApplicationRecord.status.in_(statuses))
                ).scalar() or 0
            )

    def count_records(self, *, tenant_id: str = "sd-default") -> int:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return int(
                session.execute(
                    select(func.count()).select_from(ApplicationRecord)
                    .where(ApplicationRecord.tenant_id == tenant_id)
                ).scalar() or 0
            )

    def list_records(self, *, tenant_id: str = "sd-default") -> list[ApplicationRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(
                session.execute(
                    select(ApplicationRecord)
                    .where(ApplicationRecord.tenant_id == tenant_id)
                    .order_by(ApplicationRecord.application_code)
                ).scalars()
            )

    def update_status(self, application_code: str, status: str, *, tenant_id: str = "sd-default") -> None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            session.execute(
                update(ApplicationRecord)
                .where(ApplicationRecord.tenant_id == tenant_id, ApplicationRecord.application_code == application_code)
                .values(status=status)
            )
            session.commit()

    def upsert_from_request(self, request: dict[str, Any], *, tenant_id: str = "sd-default") -> None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(
                select(ApplicationRecord).where(
                    ApplicationRecord.tenant_id == tenant_id,
                    ApplicationRecord.application_code == request["id"],
                )
            ).scalar_one_or_none()
            if record is None:
                record = ApplicationRecord(
                    tenant_id=tenant_id,
                    application_code=request["id"],
                    status=request["status"],
                    applicant_name=request["applicant"],
                    applicant_org=request["applicantDept"],
                    payload_json=safe_json(request),
                )
                session.add(record)
            else:
                record.status = request["status"]
                record.applicant_name = request["applicant"]
                record.applicant_org = request["applicantDept"]
                record.payload_json = safe_json(request)
            if request.get("source_ref"):
                upsert_legacy_mapping_in_session(
                    session,
                    {
                        "source_ref": request["source_ref"],
                        "legacy_object_ref": request.get("legacy_object_ref") or request["id"],
                        "canonical_type": "application_record",
                        "canonical_ref": request["id"],
                        "evidence_json": {"status": record.status, "resource_id": request.get("resourceId")},
                    },
                    tenant_id=tenant_id,
                )
            session.commit()
