from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select

from zw_brain.domain.models import ApprovalCaseRecord, ApprovalDecisionRecord, ApprovalStepRecord
from zw_brain.shared.db import create_session_factory


class ApprovalRepository:
    def list_cases(self) -> list[ApprovalCaseRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(session.execute(select(ApprovalCaseRecord).order_by(ApprovalCaseRecord.application_code)).scalars())

    def list_steps(self, application_code: str) -> list[ApprovalStepRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            case = session.execute(
                select(ApprovalCaseRecord).where(ApprovalCaseRecord.application_code == application_code)
            ).scalar_one_or_none()
            if case is None:
                return []
            return list(
                session.execute(
                    select(ApprovalStepRecord)
                    .where(ApprovalStepRecord.approval_case_id == case.id)
                    .order_by(ApprovalStepRecord.step_no)
                ).scalars()
            )

    def list_decisions(self, application_code: str) -> list[ApprovalDecisionRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            case = session.execute(
                select(ApprovalCaseRecord).where(ApprovalCaseRecord.application_code == application_code)
            ).scalar_one_or_none()
            if case is None:
                return []
            step_ids = [
                item.id
                for item in session.execute(
                    select(ApprovalStepRecord).where(ApprovalStepRecord.approval_case_id == case.id)
                ).scalars()
            ]
            if not step_ids:
                return []
            return list(
                session.execute(
                    select(ApprovalDecisionRecord)
                    .where(ApprovalDecisionRecord.step_id.in_(step_ids))
                    .order_by(ApprovalDecisionRecord.created_at)
                ).scalars()
            )

    def upsert_from_request_and_approval(self, request: dict[str, Any], approval: dict[str, Any], *, tenant_id: str = "default") -> None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(select(ApprovalCaseRecord).where(ApprovalCaseRecord.application_code == request["id"])).scalar_one_or_none()
            if record is None:
                record = ApprovalCaseRecord(
                    tenant_id=tenant_id,
                    application_code=request["id"],
                    current_status=request["status"],
                    current_step=1,
                    decision_payload_json=approval,
                )
                session.add(record)
                session.flush()
            else:
                record.current_status = request["status"]
                record.current_step = self._current_step_no(request["status"])
                record.decision_payload_json = approval

            session.execute(delete(ApprovalDecisionRecord).where(ApprovalDecisionRecord.step_id.in_(select(ApprovalStepRecord.id).where(ApprovalStepRecord.approval_case_id == record.id))))
            session.execute(delete(ApprovalStepRecord).where(ApprovalStepRecord.approval_case_id == record.id))

            step = ApprovalStepRecord(
                approval_case_id=record.id,
                step_no=self._current_step_no(request["status"]),
                step_name=self._step_name(request["status"]),
                decision_mode="single",
                status=self._step_status(request["status"]),
                approver_scope_json={"roles": self._approver_roles(request["status"]), "request_id": request["id"]},
            )
            session.add(step)
            session.flush()

            if approval:
                session.add(
                    ApprovalDecisionRecord(
                        step_id=step.id,
                        decision=self._decision_value(request["status"], approval),
                        decision_reason=approval.get("draftNote") or approval.get("impact"),
                        actor_snapshot_json={
                            "roles": self._approver_roles(request["status"]),
                            "suggestion": approval.get("suggestion"),
                        },
                        evidence_json={
                            "reason": approval.get("reason", []),
                            "risk": approval.get("risk", []),
                            "exceptionItems": approval.get("exceptionItems", []),
                        },
                    )
                )
            session.commit()

    def _current_step_no(self, request_status: str) -> int:
        if request_status in {"pending", "need-fix", "rejected"}:
            return 1
        if request_status == "supplementing":
            return 2
        if request_status == "summary-pending":
            return 3
        if request_status == "completed":
            return 4
        return 1

    def _step_name(self, request_status: str) -> str:
        if request_status in {"pending", "need-fix", "rejected"}:
            return "准入审批"
        if request_status == "supplementing":
            return "基层差异补录"
        if request_status == "summary-pending":
            return "汇总确认"
        if request_status == "completed":
            return "回流确认"
        return "准入审批"

    def _step_status(self, request_status: str) -> str:
        if request_status in {"pending", "supplementing", "summary-pending"}:
            return "in_progress"
        if request_status == "need-fix":
            return "returned"
        if request_status == "rejected":
            return "rejected"
        if request_status == "completed":
            return "approved"
        return "pending"

    def _approver_roles(self, request_status: str) -> list[str]:
        if request_status in {"pending", "need-fix", "rejected"}:
            return ["r2"]
        if request_status == "supplementing":
            return ["r3", "r4"]
        if request_status == "summary-pending":
            return ["r5"]
        if request_status == "completed":
            return ["r6", "r7"]
        return ["r2"]

    def _decision_value(self, request_status: str, approval: dict[str, Any]) -> str:
        suggestion = str(approval.get("suggestion", ""))
        if request_status == "need-fix" or "补正" in suggestion:
            return "return"
        if request_status == "rejected" or "驳回" in suggestion:
            return "reject"
        return "approve"
