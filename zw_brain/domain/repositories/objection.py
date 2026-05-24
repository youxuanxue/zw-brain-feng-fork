from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select

from zw_brain.domain.models import (
    ObjectionCaseRecord,
    ObjectionEvaluationRecord,
    ObjectionEvidenceRecord,
    ObjectionProcessRecord,
)
from zw_brain.domain.objection_state import (
    ALLOWED_TRANSITIONS_BY_DIMENSION,
    GENERIC_DIMENSION,
    dimension_of,
)
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.sanitization import safe_json


class ObjectionStateError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


class ObjectionRepository:
    TRANSITIONS = {
        "draft": {"submitted", "rejected"},
        "submitted": {"accepted", "rejected"},
        "accepted": {"platform_investigating", "provider_investigating"},
        "platform_investigating": {"provider_investigating", "resolved", "rejected", "escalated"},
        "provider_investigating": {"platform_investigating", "resolved", "rejected", "escalated"},
        "escalated": {"platform_investigating", "provider_investigating", "resolved", "rejected"},
        "resolved": {"closed", "provider_investigating"},
        "rejected": set(),
        "closed": set(),
    }

    def list_cases(self, *, tenant_id: str = "sd-default") -> list[ObjectionCaseRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(
                session.execute(
                    select(ObjectionCaseRecord)
                    .where(ObjectionCaseRecord.tenant_id == tenant_id)
                    .order_by(ObjectionCaseRecord.created_at)
                ).scalars()
            )

    def get_case(self, objection_id: str, *, tenant_id: str = "sd-default") -> ObjectionCaseRecord | None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return session.execute(
                select(ObjectionCaseRecord).where(
                    ObjectionCaseRecord.tenant_id == tenant_id,
                    ObjectionCaseRecord.id == objection_id,
                )
            ).scalar_one_or_none()

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

    def create_case(self, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> ObjectionCaseRecord:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = ObjectionCaseRecord(
                tenant_id=tenant_id,
                objection_kind=str(payload.get("objection_kind", payload.get("target_type", "usage"))),
                target_type=str(payload["target_type"]),
                target_id=str(payload["target_id"]),
                related_application_id=payload.get("related_application_id"),
                title=str(payload["title"]),
                complainant_org_id=str(payload.get("complainant_org_id", "unknown")),
                complainant_org_snapshot_json=safe_json(payload.get("complainant_org_snapshot_json") or {}),
                provider_org_id=str(payload.get("provider_org_id", "unknown")),
                provider_org_snapshot_json=safe_json(payload.get("provider_org_snapshot_json") or {}),
                basis_text=payload.get("basis_text"),
                expected_result=payload.get("expected_result"),
                status=str(payload.get("status", "draft")),
            )
            session.add(record)
            session.flush()
            self._add_process_in_session(
                session,
                record.id,
                node_name="创建异议",
                action_type="create",
                action_result=record.status,
                handler_snapshot_json=payload.get("actor_snapshot_json") or {},
                opinion=payload.get("basis_text"),
            )
            for evidence in payload.get("evidence", []) or []:
                self._add_evidence_in_session(session, record.id, evidence, payload.get("actor_snapshot_json") or {})
            session.commit()
            return session.execute(select(ObjectionCaseRecord).where(ObjectionCaseRecord.id == record.id)).scalar_one()

    def transition_case(
        self,
        objection_id: str,
        next_status: str,
        *,
        action_type: str,
        node_name: str,
        action_result: str = "pass",
        handler_org_id: str | None = None,
        handler_snapshot_json: dict[str, Any] | None = None,
        opinion: str | None = None,
        resolved_summary: str | None = None,
        evidence: list[dict[str, Any]] | None = None,
    ) -> ObjectionCaseRecord:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(select(ObjectionCaseRecord).where(ObjectionCaseRecord.id == objection_id)).scalar_one_or_none()
            if record is None:
                raise KeyError(objection_id)
            evidences = list(
                session.execute(
                    select(ObjectionEvidenceRecord).where(
                        ObjectionEvidenceRecord.objection_id == objection_id
                    )
                ).scalars()
            )
            self._assert_transition(record.status, next_status, dimension=dimension_of(record, evidences))
            record.status = next_status
            record.row_version += 1
            record.updated_at = _now()
            if resolved_summary is not None:
                record.resolved_summary = resolved_summary
            if next_status == "closed":
                record.closed_at = _now()
            self._add_process_in_session(
                session,
                objection_id,
                node_name=node_name,
                action_type=action_type,
                action_result=action_result,
                handler_org_id=handler_org_id,
                handler_snapshot_json=handler_snapshot_json or {},
                opinion=opinion,
            )
            for item in evidence or []:
                self._add_evidence_in_session(session, objection_id, item, handler_snapshot_json or {})
            session.commit()
            return session.execute(select(ObjectionCaseRecord).where(ObjectionCaseRecord.id == objection_id)).scalar_one()

    def add_evidence(self, objection_id: str, evidence: dict[str, Any], submitted_by: dict[str, Any] | None = None) -> ObjectionEvidenceRecord:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            if session.execute(select(ObjectionCaseRecord).where(ObjectionCaseRecord.id == objection_id)).scalar_one_or_none() is None:
                raise KeyError(objection_id)
            record = self._add_evidence_in_session(session, objection_id, evidence, submitted_by or {})
            session.commit()
            return session.execute(select(ObjectionEvidenceRecord).where(ObjectionEvidenceRecord.id == record.id)).scalar_one()

    def add_process(
        self,
        objection_id: str,
        *,
        node_name: str,
        action_type: str,
        action_result: str,
        handler_org_id: str | None = None,
        handler_snapshot_json: dict[str, Any] | None = None,
        opinion: str | None = None,
        evidence: list[dict[str, Any]] | None = None,
    ) -> ObjectionCaseRecord:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(select(ObjectionCaseRecord).where(ObjectionCaseRecord.id == objection_id)).scalar_one_or_none()
            if record is None:
                raise KeyError(objection_id)
            self._add_process_in_session(
                session,
                objection_id,
                node_name=node_name,
                action_type=action_type,
                action_result=action_result,
                handler_org_id=handler_org_id,
                handler_snapshot_json=handler_snapshot_json or {},
                opinion=opinion,
            )
            for item in evidence or []:
                self._add_evidence_in_session(session, objection_id, item, handler_snapshot_json or {})
            session.commit()
            return session.execute(select(ObjectionCaseRecord).where(ObjectionCaseRecord.id == objection_id)).scalar_one()

    def evaluate_case(self, objection_id: str, payload: dict[str, Any]) -> ObjectionEvaluationRecord:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(select(ObjectionCaseRecord).where(ObjectionCaseRecord.id == objection_id)).scalar_one_or_none()
            if record is None:
                raise KeyError(objection_id)
            if record.status != "resolved":
                raise ObjectionStateError("objection must be resolved before evaluation")
            existing = session.execute(
                select(ObjectionEvaluationRecord).where(ObjectionEvaluationRecord.objection_id == objection_id)
            ).scalar_one_or_none()
            if existing is None:
                existing = ObjectionEvaluationRecord(
                    objection_id=objection_id,
                    evaluator_snapshot_json=safe_json(payload.get("evaluator_snapshot_json") or {}),
                    solved_flag=bool(payload.get("solved_flag", True)),
                    overall_score=payload.get("overall_score"),
                    timeliness_score=payload.get("timeliness_score"),
                    result_score=payload.get("result_score"),
                    comment=payload.get("comment"),
                )
                session.add(existing)
            else:
                existing.evaluator_snapshot_json = safe_json(payload.get("evaluator_snapshot_json") or {})
                existing.solved_flag = bool(payload.get("solved_flag", True))
                existing.overall_score = payload.get("overall_score")
                existing.timeliness_score = payload.get("timeliness_score")
                existing.result_score = payload.get("result_score")
                existing.comment = payload.get("comment")
            self._add_process_in_session(
                session,
                objection_id,
                node_name="评价处理结果",
                action_type="evaluate",
                action_result="pass",
                handler_snapshot_json=payload.get("evaluator_snapshot_json") or {},
                opinion=payload.get("comment"),
            )
            session.commit()
            return session.execute(
                select(ObjectionEvaluationRecord).where(ObjectionEvaluationRecord.objection_id == objection_id)
            ).scalar_one()

    def upsert_from_dispute(self, dispute: dict[str, Any], *, tenant_id: str = "sd-default") -> None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(
                select(ObjectionCaseRecord).where(
                    ObjectionCaseRecord.tenant_id == tenant_id,
                    ObjectionCaseRecord.id == dispute["id"],
                )
            ).scalar_one_or_none()
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

    def _assert_transition(self, current: str, next_status: str, *, dimension: str = GENERIC_DIMENSION) -> None:
        allowed_table = ALLOWED_TRANSITIONS_BY_DIMENSION.get(dimension)
        if allowed_table is not None:
            allowed = allowed_table.get(current, frozenset())
            if next_status not in allowed:
                raise ObjectionStateError(
                    f"invalid {dimension}-dimension objection transition: {current} -> {next_status}"
                )
            return
        if next_status not in self.TRANSITIONS.get(current, set()):
            raise ObjectionStateError(f"invalid objection transition: {current} -> {next_status}")

    def _add_process_in_session(
        self,
        session: Any,
        objection_id: str,
        *,
        node_name: str,
        action_type: str,
        action_result: str,
        handler_org_id: str | None = None,
        handler_snapshot_json: dict[str, Any] | None = None,
        opinion: str | None = None,
    ) -> ObjectionProcessRecord:
        record = ObjectionProcessRecord(
            objection_id=objection_id,
            node_name=node_name,
            handler_org_id=handler_org_id,
            handler_snapshot_json=safe_json(handler_snapshot_json or {}),
            action_type=action_type,
            action_result=action_result,
            opinion=opinion,
        )
        session.add(record)
        return record

    def _add_evidence_in_session(
        self,
        session: Any,
        objection_id: str,
        evidence: dict[str, Any],
        submitted_by: dict[str, Any],
    ) -> ObjectionEvidenceRecord:
        record = ObjectionEvidenceRecord(
            objection_id=objection_id,
            evidence_type=str(evidence.get("evidence_type", "text")),
            content_json=safe_json(evidence.get("content_json") or evidence),
            submitted_by_json=safe_json(evidence.get("submitted_by_json") or submitted_by),
        )
        session.add(record)
        return record

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
