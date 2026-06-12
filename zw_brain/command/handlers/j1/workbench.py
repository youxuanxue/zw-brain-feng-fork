"""J1 workbench handlers — 3 cap migrated from BrainService (F1 turn 6, J1 收官)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


import copy

import zw_brain.shared.clock as clock
from zw_brain.command.brain import _DEFAULT_TENANT_ID, NotFoundError
from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.domain.workbench_backlog_projection import enrich_workbench_backlog

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _get_workbench(brain, deps, ctx, role: str) -> dict[str, Any]:
    # Action C — WorkbenchView.get_for_role defaults to {"todos": []} for missing
    # roles; we need explicit NotFoundError, so go through brain_legacy escape
    # hatch to keep the existence check. (Will retire with snapshot dict in Action D.)
    if role not in deps.brain_legacy._snapshot["workbench"]:
        raise NotFoundError(role)
    view = deps.view.workbench.get_for_role(role)
    # 工作台 enrich 覆盖全部 5 角色（D57②/R-8）：业务运营员待办整体替换为真实积压（D53⑤
    # 发布类五项，每条深链既有办理页、零积压不投）；管理员叠加供数审核待办；操作员维持
    # 「申请进度」形态、办理建议真实现算；安全审计员=纯只读监督概览；运维员=运维核查。
    # 「待受理异议」深链 /provider/inbox/objection 已随 D57① 接通受理面（submitted 纳入
    # 收件箱 + objection.case.accept 可点），原「待裁决后校准」注记已闭合。
    # 投影口径单一事实源见 workbench_backlog_projection.enrich_workbench_backlog。
    return enrich_workbench_backlog(view, role)

def _submit_service_rating(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    """申请人 完成交付后为本次共享服务打分（写入审计供 安全审计员 督查可见）。"""
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    task_id = str(payload.get("task_id") or payload.get("delivery_task_id") or "")
    score = int(payload.get("score", 5))
    comment = str(payload.get("comment", "")).strip()

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        task = deps.view.delivery.find_by_id(task_id) if task_id else None
        if task is not None:
            task.setdefault("rating", {})
            task["rating"]["score"] = score
            task["rating"]["comment"] = comment
            task["rating"]["ratedBy"] = actor
            task["rating"]["ratedAt"] = clock.now_datetime()
            task.setdefault("history", []).append({"time": clock.now_short_time(), "state": f"服务评价：{score} 星", "detail": comment or "—"})
        deps.append_audit_feed("service.rating.submit", task_id, "ok", actor)
        return {"task_id": task_id, "score": score, "comment": comment, "audit_id": audit_id}

    return deps.write(ctx, payload, mutation)

def _terminate_subscription(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    subscription_code = str(payload["subscription_code"])
    reason = str(payload["reason"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        from sqlalchemy import select  # noqa: PLC0415

        from zw_brain.domain.models import DeliverySubscriptionRecord  # noqa: PLC0415
        from zw_brain.shared.db import create_session_factory  # noqa: PLC0415

        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            rec = session.execute(
                select(DeliverySubscriptionRecord)
                .where(DeliverySubscriptionRecord.tenant_id == _DEFAULT_TENANT_ID)
                .where(DeliverySubscriptionRecord.subscription_code == subscription_code)
            ).scalar_one_or_none()
            if rec is None:
                raise NotFoundError(subscription_code)
            rec.status = "terminated"
            snapshot = copy.deepcopy(rec.legacy_status_snapshot_json or {})
            snapshot.setdefault("terminations", []).append({"audit_id": audit_id, "reason": reason, "actor": actor})
            rec.legacy_status_snapshot_json = snapshot
            session.commit()
        deps.append_audit_feed("subscription.terminate", subscription_code, "ok", actor)
        return {"subscription_code": subscription_code, "status": "terminated", "audit_id": audit_id}

    return deps.write(ctx, payload, mutation)


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_workbench_view(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _get_workbench(brain, deps, ctx, str(payload.get("role", ctx.role)))

def handler_service_rating_submit(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _submit_service_rating(brain, deps, ctx, payload)

def handler_subscription_terminate(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _terminate_subscription(brain, deps, ctx, payload)

