"""J1 application_grant handlers — 4 cap migrated from BrainService (F1 turn 6, J1 收官)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

import zw_brain.shared.clock as clock
from zw_brain.command.brain import BrainServiceError
from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.domain.errors import AccessDeniedError, InvalidStateError

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _approve_application_grant(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    decision = str(payload["decision"])
    if decision == "approve":
        return brain.grant_delivery_access(str(payload["task_id"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))
    if decision in {"reject", "return_for_fix"}:
        task_id = str(payload["task_id"])
        role = str(payload.get("role", ctx.role))
        confirmed = bool(payload.get("confirmed"))

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            task = deps.view.delivery.find_by_id(task_id)
            task["status"] = "warning"
            task["updatedAt"] = clock.now_datetime()
            task["note"] = str(payload.get("reason", "授权申请未通过。"))
            task.setdefault("history", []).append({"time": clock.now_short_time(), "state": "授权未通过", "detail": task["note"]})
            deps.append_audit_feed("application.grant.approve", task_id, "warning", actor)
            return {"task_id": task_id, "decision": decision, "status": task["status"], "audit_id": audit_id}

        return deps.write(ctx, payload, mutation)
    raise BrainServiceError(f"unsupported grant decision: {decision}")

def _renew_application_grant(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    # Customer surface forwards `delivery_task_id`; the legacy contract used
    # `task_id`. Accept either so the same skill works from both call sites.
    task_id = str(payload.get("task_id") or payload.get("delivery_task_id"))

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        task = deps.view.delivery.find_by_id(task_id)
        task.setdefault("access", {})["renew_until"] = payload.get("renew_until")
        task["updatedAt"] = clock.now_datetime()
        task.setdefault("history", []).append({"time": clock.now_short_time(), "state": "授权已续期", "detail": str(payload.get("reason", "访问授权续期完成。"))})
        deps.repos.delivery.add_execution_evidence({"evidence_ref": audit_id, "delivery_code": task_id, "executor_kind": "grant_policy", "evidence_kind": "grant_renewal", "result_status": "renewed", "payload_json": payload})
        deps.append_audit_feed("application.grant.renew", task_id, "ok", actor)
        return {"task_id": task_id, "renew_until": payload.get("renew_until"), "audit_id": audit_id}

    return deps.write(ctx, payload, mutation)

def _resolve_grant_target_id(payload: dict[str, Any]) -> str:
    """Pull the application id from either contract spelling.

    H4 fix: callers may forward ``request_id`` (canonical) or
    ``delivery_task_id`` (legacy delivery surface). An empty / missing id is a
    caller error — we raise instead of silently treating it as "nothing to do".
    """
    request_id = str(payload.get("request_id") or payload.get("delivery_task_id") or "").strip()
    if not request_id:
        raise InvalidStateError("撤回 / 暂停授权需指定申请单号（request_id 或 delivery_task_id）。")
    return request_id

def _suspend_application_grant(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    """业务运营员 暂停已生效的授权 — 申请人 暂时无法访问但授权不失效，可恢复（决策 A）。"""
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    request_id = _resolve_grant_target_id(payload)

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        # H4 fix: 找不到目标申请 → find_by_id 抛 NotFoundError；不再静默跳过却返回 ok。
        request = deps.view.requests.find_by_id(request_id)
        if bool(request.get("grant", {}).get("revoked")) or str(request.get("status")) == "revoked":
            raise InvalidStateError("该授权已收回，无法暂停；如需重新使用请重新提交申请。")
        # R-001 fix: 暂停必须落 status（PersistMiddleware 只回写 status 列，grant 子字典
        # 不入库）。旧实现只置 grant['suspended']=True 而无人消费、又不持久化 → 返回
        # {suspended:True} 假成功，刷新即消失、申请人并未真被挡。与 revoke 置 status
        # 对称：status='suspended' 才让 UI 显示「已暂停」、暂停按钮自隐、并真落库。
        # （恢复/resume 能力待后续 PR；本次先消除假成功，暂停态可被 revoke 终结。）
        request.setdefault("grant", {})["suspended"] = True
        request["status"] = "suspended"
        # R-004 fix: 真实库申请（M0 导入、hex id）不在内存快照里 → find_by_id 返回 DB
        # 派生的一次性副本，PersistMiddleware 只回写 brain._snapshot["requests"] → 副本
        # 改动落不了库（返回 ok 却 DB 不变 = 假成功，且不可逆守卫永不触发可无限点）。
        # 直接经 application_repo 把 status 写回 application_record（demo REQ-* 同有 DB 行，
        # update_status 按 application_code 命中，双写一致；纯内存 demo 无行则 no-op）。
        deps.repos.application.update_status(request_id, "suspended")
        request.setdefault("timeline", []).append({"label": "授权已暂停", "time": clock.now_datetime(), "note": str(payload.get("reason", "业务运营员 临时暂停以核实使用边界。"))})
        deps.append_audit_feed("application.grant.suspend", request_id, "ok", actor)
        return {"request_id": request_id, "suspended": True, "audit_id": audit_id}

    return deps.write(ctx, payload, mutation)

def _revoke_application_grant(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    """收回已生效的授权 — 业务运营员 合规收回 或 申请人本人 主动放弃；永久不可逆，需重新申请。

    决策 A（已签字）：撤回归 ROLE_BUSIAUDIT（合规驱动）与 ROLE_ORGAN_OPERATER（申请人主动放弃）。
    申请人路径走 owner 校验（只能放弃本人提交的申请）；业务运营员路径无 owner 限制（合规职责）。
    """
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    request_id = _resolve_grant_target_id(payload)
    is_applicant = role == "ROLE_ORGAN_OPERATER"
    if not is_applicant and role != "ROLE_BUSIAUDIT":
        # 角色层级 ROLE_HIERARCHY 中 MANAGER ⊇ OPERATER，会让 MANAGER 经继承命中 revoke
        # 权限位；但 SPEC 负向场景「提供方部门管理员不直接撤回」+ 决策 A「收回 MANAGER」要求
        # 合规撤回仅业务运营员。故在 handler 显式收口：非申请人路径只认 BUSIAUDIT，其余拒绝。
        raise AccessDeniedError("仅业务运营员可合规收回授权；部门管理员请通过提交使用异议路径处理。")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        # H4 fix: 找不到目标申请 → find_by_id 抛 NotFoundError；不再静默跳过却返回 ok。
        request = deps.view.requests.find_by_id(request_id)
        if bool(request.get("grant", {}).get("revoked")) or str(request.get("status")) == "revoked":
            # SPEC「撤回不可逆」：已撤回再撤回是无效状态转换，诚实报错而非二次假成功。
            raise InvalidStateError("该授权已收回，无需重复撤回；如需重新使用请重新提交申请。")
        if is_applicant and str(request.get("applicant", "")) != actor:
            # SPEC 负向：申请人不能放弃他人的授权。owner 校验在身份粒度（角色 actor，
            # request.create 时 applicant=actor）——历史导入申请 applicant 为脱敏名/他人 →
            # 拒绝（reason=not_owner_of_application）；逐人 owner 待真实 IAM 落地。
            raise AccessDeniedError("not_owner_of_application: 只能放弃本人提交的申请的授权。")
        initiated_by = "applicant" if is_applicant else "busiaudit"
        request.setdefault("grant", {})["revoked"] = True
        request["grant"]["initiated_by"] = initiated_by
        request["status"] = "revoked"
        # R-004 fix: 真实库申请经 application_repo 落库，否则副本改动丢失、返回 revoked:true 却
        # DB 不变（假成功），不可逆守卫拿 DB 现状判定永远放行可重复撤回。
        deps.repos.application.update_status(request_id, "revoked")
        note = (
            str(payload["reason"]) if payload.get("reason")
            else ("申请人主动放弃授权。" if is_applicant else "业务运营员 合规收回授权，需重新申请。")
        )
        request.setdefault("timeline", []).append({"label": "授权已收回", "time": clock.now_datetime(), "note": note})
        deps.append_audit_feed("application.grant.revoke", request_id, "ok", actor)
        return {"request_id": request_id, "revoked": True, "initiated_by": initiated_by, "audit_id": audit_id}

    return deps.write(ctx, payload, mutation)


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_application_grant_approve(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _approve_application_grant(brain, deps, ctx, payload)

def handler_application_grant_renew(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _renew_application_grant(brain, deps, ctx, payload)

def handler_application_grant_suspend(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _suspend_application_grant(brain, deps, ctx, payload)

def handler_application_grant_revoke(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _revoke_application_grant(brain, deps, ctx, payload)

