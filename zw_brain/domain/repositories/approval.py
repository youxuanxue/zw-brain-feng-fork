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

    def upsert_api_resource_lifecycle(
        self,
        resource_code: str,
        status: str,
        *,
        actor: str,
        skill_id: str,
        audit_id: str,
        decision: str | None = None,
        tenant_id: str = "default",
    ) -> None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            case = session.execute(
                select(ApprovalCaseRecord).where(
                    ApprovalCaseRecord.tenant_id == tenant_id,
                    ApprovalCaseRecord.application_code == resource_code,
                )
            ).scalar_one_or_none()
            if case is not None and case.decision_payload_json.get("audit_id") == audit_id:
                return

            if case is None:
                case = ApprovalCaseRecord(
                    tenant_id=tenant_id,
                    application_code=resource_code,
                    current_status=status,
                    current_step=self._api_step_no(status),
                    decision_payload_json={
                        "resource_code": resource_code,
                        "status": status,
                        "skill_id": skill_id,
                        "audit_id": audit_id,
                    },
                )
                session.add(case)
                session.flush()
            else:
                case.current_status = status
                case.current_step = self._api_step_no(status)
                case.decision_payload_json = {
                    **case.decision_payload_json,
                    "resource_code": resource_code,
                    "status": status,
                    "skill_id": skill_id,
                    "audit_id": audit_id,
                }

            step = ApprovalStepRecord(
                approval_case_id=case.id,
                step_no=self._api_step_no(status),
                step_name=self._api_step_name(status),
                decision_mode="single",
                status=self._api_step_status(status),
                approver_scope_json={"roles": self._api_approver_roles(status), "resource_code": resource_code},
            )
            session.add(step)
            session.flush()
            session.add(
                ApprovalDecisionRecord(
                    step_id=step.id,
                    decision=decision or self._api_decision_value(status),
                    decision_reason=f"{skill_id} via {audit_id}",
                    actor_snapshot_json={"actor": actor, "roles": self._api_approver_roles(status)},
                    evidence_json={"resource_code": resource_code, "status": status, "audit_id": audit_id},
                )
            )
            session.commit()

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

    def _api_step_no(self, status: str) -> int:
        if status in {"draft", "pending_review"}:
            return 1
        if status == "approved":
            return 2
        if status == "active":
            return 3
        if status in {"retired", "revoked"}:
            return 4
        if status == "test_failed":
            return 2
        return 1

    def _api_step_name(self, status: str) -> str:
        if status == "pending_review":
            return "API 服务资源审核"
        if status == "approved":
            return "API 服务资源审核通过"
        if status == "active":
            return "API 服务资源发布"
        if status == "retired":
            return "API 服务资源撤回"
        if status == "revoked":
            return "API 服务资源撤销授权"
        if status == "test_failed":
            return "API 服务连通性测试失败"
        return "API 服务资源草稿"

    def _api_step_status(self, status: str) -> str:
        if status == "pending_review":
            return "in_progress"
        if status in {"approved", "active"}:
            return "approved"
        if status in {"retired", "revoked"}:
            return "closed"
        if status == "test_failed":
            return "returned"
        return "pending"

    def _api_approver_roles(self, status: str) -> list[str]:
        if status in {"pending_review", "approved", "active", "retired", "revoked", "test_failed"}:
            return ["r7"]
        return ["r6", "r7"]

    def _api_decision_value(self, status: str) -> str:
        if status in {"approved", "active"}:
            return "approve"
        if status in {"retired", "revoked"}:
            return "close"
        if status == "test_failed":
            return "return"
        if status == "pending_review":
            return "submit"
        return "draft"

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
