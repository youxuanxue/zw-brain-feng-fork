from __future__ import annotations

from typing import Any

from sqlalchemy import select

from zw_brain.domain.models import ApplicationRecord
from zw_brain.shared.db import create_session_factory


class ApplicationRepository:
    def list_records(self) -> list[ApplicationRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(session.execute(select(ApplicationRecord).order_by(ApplicationRecord.application_code)).scalars())

    def upsert_from_request(self, request: dict[str, Any], *, tenant_id: str = "default") -> None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(select(ApplicationRecord).where(ApplicationRecord.application_code == request["id"])).scalar_one_or_none()
            if record is None:
                record = ApplicationRecord(
                    tenant_id=tenant_id,
                    application_code=request["id"],
                    status=request["status"],
                    applicant_name=request["applicant"],
                    applicant_org=request["applicantDept"],
                    payload_json=request,
                )
                session.add(record)
            else:
                record.status = request["status"]
                record.applicant_name = request["applicant"]
                record.applicant_org = request["applicantDept"]
                record.payload_json = request
            session.commit()
