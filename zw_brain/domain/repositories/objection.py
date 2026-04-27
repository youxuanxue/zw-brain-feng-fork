from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select

from zw_brain.domain.models import (
    ObjectionCaseRecord,
    ObjectionEvaluationRecord,
    ObjectionEvidenceRecord,
    ObjectionProcessRecord,
)
from zw_brain.shared.db import create_session_factory


class ObjectionRepository:
    def list_cases(self) -> list[ObjectionCaseRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(session.execute(select(ObjectionCaseRecord).order_by(ObjectionCaseRecord.created_at)).scalars())

    def get_case(self, objection_id: str) -> ObjectionCaseRecord | None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return session.execute(select(ObjectionCaseRecord).where(ObjectionCaseRecord.id == objection_id)).scalar_one_or_none()

    def list_processes(self, objection_id: str) -> list[ObjectionProcessRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(
                session.execute(
                    select(ObjectionProcessRecord)
                    .where(ObjectionProcessRecord.objection_id == objection_id)
                    .order_by(ObjectionProcessRecord.created_at)
                ).scalars()
            )

    def list_evidence(self, objection_id: str) -> list[ObjectionEvidenceRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(
                session.execute(
                    select(ObjectionEvidenceRecord)
                    .where(ObjectionEvidenceRecord.objection_id == objection_id)
                    .order_by(ObjectionEvidenceRecord.created_at)
                ).scalars()
            )

    def get_evaluation(self, objection_id: str) -> ObjectionEvaluationRecord | None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return session.execute(
                select(ObjectionEvaluationRecord).where(ObjectionEvaluationRecord.objection_id == objection_id)
            ).scalar_one_or_none()

    def upsert_from_dispute(self, dispute: dict[str, Any], *, tenant_id: str = "default") -> None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(select(ObjectionCaseRecord).where(ObjectionCaseRecord.id == dispute["id"])).scalar_one_or_none()
            if record is None:
                record = ObjectionCaseRecord(
                    id=dispute["id"],
                    tenant_id=tenant_id,
                    objection_kind="usage",
                    target_type="alert",
                    target_id=dispute["id"],
                    related_application_id=None,
                    title=dispute["title"],
                    complainant_org_id=dispute["owner"],
                    complainant_org_snapshot_json={"owner": dispute["owner"]},
                    provider_org_id=dispute["owner"],
                    provider_org_snapshot_json={"owner": dispute["owner"]},
                    basis_text=dispute.get("aiSummary"),
                    expected_result="完成治理闭环",
                    status=self._map_status(dispute["status"]),
                    resolved_summary=dispute.get("aiSummary") if dispute["status"] == "resolved" else None,
                )
                session.add(record)
                session.flush()
            else:
                record.title = dispute["title"]
                record.complainant_org_id = dispute["owner"]
                record.complainant_org_snapshot_json = {"owner": dispute["owner"]}
                record.provider_org_id = dispute["owner"]
                record.provider_org_snapshot_json = {"owner": dispute["owner"]}
                record.basis_text = dispute.get("aiSummary")
                record.status = self._map_status(dispute["status"])
                record.resolved_summary = dispute.get("aiSummary") if dispute["status"] == "resolved" else None

            session.execute(delete(ObjectionProcessRecord).where(ObjectionProcessRecord.objection_id == record.id))
            session.execute(delete(ObjectionEvidenceRecord).where(ObjectionEvidenceRecord.objection_id == record.id))
            session.execute(delete(ObjectionEvaluationRecord).where(ObjectionEvaluationRecord.objection_id == record.id))

            for step in dispute.get("timeline", []):
                session.add(
                    ObjectionProcessRecord(
                        objection_id=record.id,
                        node_name=step["label"],
                        handler_org_id=dispute["owner"],
                        handler_snapshot_json={"owner": dispute["owner"]},
                        action_type=self._map_action_type(step["label"]),
                        action_result=self._map_action_result(dispute["status"]),
                        opinion=step.get("note"),
                    )
                )
                session.add(
                    ObjectionEvidenceRecord(
                        objection_id=record.id,
                        evidence_type="text",
                        content_json={"time": step["time"], "note": step.get("note"), "label": step["label"]},
                        submitted_by_json={"owner": dispute["owner"]},
                    )
                )

            session.add(
                ObjectionEvaluationRecord(
                    objection_id=record.id,
                    evaluator_snapshot_json={"owner": dispute["owner"]},
                    solved_flag=dispute["status"] == "resolved",
                    overall_score=100 if dispute["status"] == "resolved" else None,
                    comment=dispute.get("aiSummary"),
                )
            )
            session.commit()

    def _map_status(self, status: str) -> str:
        mapping = {
            "open": "submitted",
            "escalated": "platform_investigating",
            "resolved": "resolved",
        }
        return mapping.get(status, "submitted")

    def _map_action_type(self, label: str) -> str:
        if "受理" in label:
            return "accept"
        if "调查" in label or "核查" in label:
            return "investigate"
        if "升级" in label:
            return "transfer"
        if "修正" in label or "已修正" in label:
            return "resolve"
        return "investigate"

    def _map_action_result(self, status: str) -> str:
        if status == "resolved":
            return "closed"
        return "pass"
