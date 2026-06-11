"""ConditionalApprovalService — J1 有条件共享分支两级受理/审核运行时.

SPEC: .testing/waves/wave-0-golden-path/features/j1-approval-conditional.feature

D55/P21（受理/审核两级，改 D49 关联）：有条件共享资源 (shared_type=2) 走两级，
**受理在前、部门审核在后**（与旧序对调）：
  1. accept（受理，第一级）— 业务运营员 (ROLE_BUSIAUDIT)，submitted(1 待审) → dept_approved(4
     受理通过/待部门审中间态)；受理驳回 submitted → rejected(3)。受理=初级审核，是平台级动作，
     不适用 self_approval / R11 方向 guard（业务运营员是省大数据局平台方，无提供方部门方向概念）。
     复用 application.platform_approve.execute key（API surface 稳定，D33 先例；handler/方法名
     保留 platform_*，语义已是「受理」）。
  2. dept_review（部门审核，第二级）— 提供方部门管理员 (ROLE_ORGAN_MANAGER)，dept_approved(4)
     → granted(6 已授权)；审核驳回 dept_approved → rejected(3)，受理记录保留。self_approval /
     R11 方向 guard 保留在本部门审核级。复用 application.dept_approve.execute key（resubmit
     补件重提共用本 key 走申请人路径，OPERATER 发起）。审批通过自动签发凭据在本终审级触发。

驳回后申请人补件重提：rejected(3) → submitted(1)，round +1。

**状态字符串与迁移表保持不变**（``dept_approved`` 内部枚举不改名——API surface / 国家转报
escalate 路径键此态，D33/D48 边稳定；其「含义」由受理通过变为「受理通过待部门审」，用户可见
文案由 status_text/statusLabels 承载）。状态机迁移由 ``CONDITIONAL_TRANSITIONS`` 闭包；任何
非法迁移 raise InvalidStateError（entry 层映射 409）。

写库经 ``approval_repo.append_conditional_step`` + ``application_repo.update_status``
（仅 adapters/legacy 之外的 ORM 写路径走 repo），审计 / capability_call 经
``brain._mutate``（ctx.skill_id 即 capability_call 名）。
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from zw_brain.domain import policy
from zw_brain.domain.errors import InvalidStateError, NotFoundError
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService


# Canonical application status ↔ legacy int (SPEC 末尾状态机表)
STATUS_SUBMITTED = "submitted"        # 1 待审
STATUS_REJECTED = "rejected"          # 3 驳回
STATUS_DEPT_APPROVED = "dept_approved"  # 4 受理通过/待部门审（中间态；D55/P21 后含义=已受理待部门审核）
STATUS_GRANTED = "granted"            # 6 已授权

LEGACY_STATUS = {
    STATUS_SUBMITTED: 1,
    STATUS_REJECTED: 3,
    STATUS_DEPT_APPROVED: 4,
    STATUS_GRANTED: 6,
}

# 合法迁移闭包（基线 §3.3 + SPEC 回归场景表）。actor 维度由 handler 权限 + guard 守，
# 此表只裁状态对是否合法。
# D55/P21：迁移对（状态字符串）不变；actor 含义已对调——submitted→dept_approved 现由「受理
# （业务运营员，第一级）」产生，dept_approved→granted 现由「部门审核（部门管理员，第二级终审）」产生。
CONDITIONAL_TRANSITIONS: dict[str, set[str]] = {
    STATUS_SUBMITTED: {STATUS_DEPT_APPROVED, STATUS_REJECTED, STATUS_GRANTED},  # accept(受理)→受理通过/受理驳回 / 无条件受理即终→granted
    STATUS_DEPT_APPROVED: {STATUS_GRANTED, STATUS_REJECTED},                    # dept_review(部门审核终审) approve/reject
    STATUS_REJECTED: {STATUS_SUBMITTED},                                        # applicant.resubmit
    STATUS_GRANTED: set(),                                                      # 终态（收回走 grant.revoke，独立 cap）
}


def assert_legal_transition(from_status: str, to_status: str) -> None:
    allowed = CONDITIONAL_TRANSITIONS.get(from_status)
    if allowed is None or to_status not in allowed:
        raise InvalidStateError(
            f"illegal conditional approval transition: {from_status!r} → {to_status!r}; "
            f"allowed from {from_status!r}: {sorted(allowed or set()) or '∅'}"
        )


@dataclass(frozen=True)
class ConditionalApprovalService:
    """J1 有条件共享两步审批 (dept.approve → platform.approve / reject + resubmit)."""

    brain: BrainService

    # --- helpers -----------------------------------------------------------

    def _store(self) -> Any:
        store = getattr(getattr(self.brain, "_state_store", None), "database_store", None)
        if store is None:
            raise NotFoundError("database store unavailable")
        return store

    def _record(self, store: Any, request_id: str) -> Any:
        record = store.application_repo.get_record(request_id, tenant_id=_DEFAULT_TENANT_ID)
        if record is None:
            raise NotFoundError(request_id)
        return record

    @staticmethod
    def _payload(record: Any) -> dict[str, Any]:
        return copy.deepcopy(record.payload_json or {})

    @staticmethod
    def owner_org_code(payload: dict[str, Any]) -> str:
        """资源提供方部门 org_code（R11 方向源）。"""
        return str(
            payload.get("owner_org_code")
            or payload.get("resource_owner_org_code")
            or (payload.get("reuseCandidate") or {}).get("owner_org_code")
            or ""
        )

    @staticmethod
    def shared_type(payload: dict[str, Any]) -> int:
        raw = payload.get("shared_type")
        try:
            return int(raw) if raw is not None else 0
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def applicant_org_code(payload: dict[str, Any], record: Any) -> str:
        return str(payload.get("applicant_org_code") or record.applicant_org or "")

    # --- 第二级: 部门管理员审核（终审） ------------------------------------
    # D55/P21：方法名 dept_approve 保留（key application.dept_approve）；语义现为「第二级部门
    # 审核终审」——前置态从 submitted 改为 dept_approved（受理后），target 终审 granted。

    def dept_approve(
        self,
        request_id: str,
        role: str,
        confirmed: bool,
        *,
        actor_org_code: str,
        decision: str,
        note: str = "",
        skill_id: str = "application.dept_approve",
    ) -> dict[str, Any]:
        """第二级部门审核（终审）：dept_approved → granted（通过）/ rejected（驳回）。

        decision ∈ {'approve', 'reject'}。enforce self_approval + R11 方向（保留在本级）。
        前置态须为 dept_approved（业务运营员已受理）；驳回时受理记录保留（append-only）。
        审批通过自动签发凭据（平台自签，C-1 凭据诚实化）。
        """
        store = self._store()
        record = self._record(store, request_id)
        payload = self._payload(record)
        if record.status != STATUS_DEPT_APPROVED:
            raise InvalidStateError(
                f"dept_approve（第二级部门审核）requires status={STATUS_DEPT_APPROVED!r}; got {record.status!r}"
            )
        owner_org = self.owner_org_code(payload)
        applicant_org = self.applicant_org_code(payload, record)
        # Scenario 6: 申请人本人不能审批自己的申请（policy reject + audit）
        policy.enforce_self_approval_guard(applicant_org, actor_org_code)
        # Scenario 5: 提供方部门外的 ORGAN_MANAGER 不能审批此申请（R11 方向）
        policy.enforce_dept_approval_direction(owner_org, actor_org_code)

        target = STATUS_GRANTED if decision == "approve" else STATUS_REJECTED
        assert_legal_transition(record.status, target)
        approve_org_name = str(payload.get("owner_org_name") or owner_org)

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            store.approval_repo.append_conditional_step(
                request_id,
                decision_mode="department",
                step_name=f"部门审-{approve_org_name}" if approve_org_name else "部门管理员审核",
                step_status="completed",
                decision="approved" if decision == "approve" else "rejected",
                reason=note,
                actor=actor,
                actor_role=role,
                approver_scope={
                    "owner_org_code": owner_org,
                    "approve_org_code": actor_org_code,
                    "approve_org_name": approve_org_name,
                },
                skill_id=skill_id,
                audit_id=audit_id,
                case_status=target,
                tenant_id=_DEFAULT_TENANT_ID,
            )
            new_payload = dict(payload)
            new_payload["dept_approver_id"] = actor
            new_payload["dept_approver_org_code"] = actor_org_code
            new_payload["dept_decided_at"] = audit_id  # audit_id is timestamp-derived in pipeline; kept as decision marker
            new_payload["dept_decision"] = decision
            new_payload["dept_decision_note"] = note
            self._persist_payload(store, request_id, new_payload, target)
            self.brain._append_audit_feed(skill_id, f"{request_id}:{decision}", "ok" if decision == "approve" else "warning", actor)
            return {
                "request_id": request_id,
                "status": target,
                "legacy_status": LEGACY_STATUS[target],
                "decision": decision,
                "dept_approver_id": actor,
                "step": "dept_approve",
            }

        result = self.brain._mutate(skill_id, role, confirmed, {"request_id": request_id, "decision": decision}, mutation)
        if decision == "approve":
            # 终审通过自动签发凭据（平台自签，C-1 凭据诚实化）。
            self.brain._auto_issue_credential_on_approval(request_id, role, self.brain._actor_for_role(role))
        return result

    # --- 第一级: 业务运营员受理（初级审核） --------------------------------
    # D55/P21：方法名 platform_decide 保留（key application.platform_approve）；语义现为「第一级
    # 受理（初级审核）」——前置态 submitted，受理通过 → dept_approved 中间态。受理是平台级动作，
    # 不适用 self_approval / R11 方向 guard。

    def platform_decide(
        self,
        request_id: str,
        role: str,
        confirmed: bool,
        *,
        actor_org_code: str,
        decision: str,
        note: str = "",
        skill_id: str = "application.platform_approve",
    ) -> dict[str, Any]:
        """第一级受理（初级审核）：submitted → dept_approved（受理通过）/ rejected（受理驳回）。

        decision ∈ {'approve', 'reject'}。受理是平台级动作，不做 self/方向校验。
        """
        store = self._store()
        record = self._record(store, request_id)
        payload = self._payload(record)
        if record.status != STATUS_SUBMITTED:
            raise InvalidStateError(
                f"platform_approve（第一级受理）requires status={STATUS_SUBMITTED!r}; got {record.status!r}"
            )
        target = STATUS_DEPT_APPROVED if decision == "approve" else STATUS_REJECTED
        assert_legal_transition(record.status, target)

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            store.approval_repo.append_conditional_step(
                request_id,
                decision_mode="single",
                step_name="受理",
                step_status="completed",
                # decision 存 "approved"/"rejected"（下游按 decision=="approved" 过滤）。
                decision="approved" if decision == "approve" else "rejected",
                reason=note,
                actor=actor,
                actor_role=role,
                approver_scope={
                    "owner_org_code": self.owner_org_code(payload),
                    "approve_org_code": actor_org_code,
                    "platform_review": True,
                    "stage": "accept",
                },
                skill_id=skill_id,
                audit_id=audit_id,
                case_status=target,
                tenant_id=_DEFAULT_TENANT_ID,
            )
            new_payload = dict(payload)
            new_payload["platform_reviewer_id"] = actor
            new_payload["platform_decision"] = decision
            new_payload["platform_decision_note"] = note
            self._persist_payload(store, request_id, new_payload, target)
            self.brain._append_audit_feed(skill_id, f"{request_id}:{decision}", "ok" if decision == "approve" else "warning", actor)
            return {
                "request_id": request_id,
                "status": target,
                "legacy_status": LEGACY_STATUS[target],
                "decision": decision,
                "platform_reviewer_id": actor,
                "step": "platform_approve",
            }

        return self.brain._mutate(skill_id, role, confirmed, {"request_id": request_id, "decision": decision}, mutation)

    # --- applicant resubmit ------------------------------------------------

    def applicant_resubmit(
        self,
        request_id: str,
        role: str,
        confirmed: bool,
        *,
        actor_org_code: str,
        skill_id: str = "application.dept_approve",
    ) -> dict[str, Any]:
        """补件重提：rejected → submitted，round +1（业务反馈 #4）。

        申请人本人操作（applicant_org_code 必须等于申请单 applicant_org）。
        """
        store = self._store()
        record = self._record(store, request_id)
        payload = self._payload(record)
        if record.status != STATUS_REJECTED:
            raise InvalidStateError(
                f"resubmit requires status={STATUS_REJECTED!r}; got {record.status!r}"
            )
        assert_legal_transition(record.status, STATUS_SUBMITTED)
        applicant_org = self.applicant_org_code(payload, record)
        if applicant_org and actor_org_code and applicant_org != actor_org_code:
            raise policy.ApprovalDirectionError(
                f"resubmit_must_be_applicant: applicant_org={applicant_org!r} actor_org={actor_org_code!r}"
            )

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            new_payload = dict(payload)
            new_payload["round"] = int(payload.get("round") or 1) + 1
            self._persist_payload(store, request_id, new_payload, STATUS_SUBMITTED)
            self.brain._append_audit_feed(skill_id, f"{request_id}:resubmit", "ok", actor)
            return {
                "request_id": request_id,
                "status": STATUS_SUBMITTED,
                "legacy_status": LEGACY_STATUS[STATUS_SUBMITTED],
                "round": new_payload["round"],
                "step": "resubmit",
            }

        return self.brain._mutate(skill_id, role, confirmed, {"request_id": request_id, "decision": "resubmit"}, mutation)

    # --- shared write helper ----------------------------------------------

    def _persist_payload(self, store: Any, request_id: str, payload: dict[str, Any], status: str) -> None:
        """Persist both status and payload back to the application record.

        Action D：运行时单优先走 CardSession 登记卡（状态机增记字段合入卡、
        写括号末尾 flush 落库；同 dispatch 内后续读取——如终审后嵌套的凭据
        自动签发——拿到的就是新态，无陈旧可言）。legacy 导入单不进会话，
        保持直接 ``upsert_from_request``（ORM upsert，无裸 SQL），round /
        dept_approver_id 等 payload 字段随之存续。
        """
        card = self.brain._card_session.get_request(request_id)
        if card is not None:
            for key, value in payload.items():
                if key not in {"id", "status"}:
                    card[key] = value
            card["status"] = status
            return
        record = store.application_repo.get_record(request_id, tenant_id=_DEFAULT_TENANT_ID)
        request_shaped = {
            "id": request_id,
            "status": status,
            "applicant": record.applicant_name,
            "applicantDept": record.applicant_org,
            **{k: v for k, v in payload.items() if k not in {"id", "status", "applicant", "applicantDept"}},
        }
        store.application_repo.upsert_from_request(request_shaped, tenant_id=_DEFAULT_TENANT_ID)
