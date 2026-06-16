"""J1 workbench handlers — 3 cap migrated from BrainService (F1 turn 6, J1 收官)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


import zw_brain.shared.clock as clock
from zw_brain.command.brain import NotFoundError
from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.domain.services.reference_service import ReferenceService
from zw_brain.domain.workbench_backlog_projection import enrich_workbench_backlog
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id
from zw_brain.shared.session_context import caller_org_code

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _session_greeting(payload: dict[str, Any]) -> str:
    """问候语 = 真实会话身份带出（#258 复审 R-004，D11 真实库精神）。

    seed 虚构人物名（周处长/刘主任/高主任/林督查）已随本修复从 seed_snapshot 整体退役；
    问候语不再来自 seed，而是按当前会话现算：
    - 经 BFF trust-stamp 路径（REST/IAM 与 dev-bypass 同路）payload 携带 actor_snapshot，
      display_name 取自 actor_projection（IAM 登录）或会话身份标签（dev-bypass=「本地调试」）；
    - 取不到（in-process / 测试 / 离线）诚实回落纯时段问候，不捏造姓名头衔（R12 业务用语）。
    """
    from datetime import datetime  # noqa: PLC0415

    snapshot = payload.get("actor_snapshot")
    name = ""
    if isinstance(snapshot, dict):
        name = str(snapshot.get("display_name") or "").strip()
    hour = datetime.now().hour
    if 5 <= hour < 12:
        tod = "上午好"
    elif 12 <= hour < 18:
        tod = "下午好"
    else:
        tod = "晚上好"
    return f"{name}，{tod}" if name else tod


def _get_workbench(brain, deps, ctx, role: str, payload: dict[str, Any]) -> dict[str, Any]:
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
    # 部门数据可见域：管理员待办按本机构(+下级)收口（M8 落），全局角色 None 放行平台待办。
    tenant_id = str(payload.get("tenant_id") or get_runtime_tenant_id())
    visible_org_codes = ReferenceService().visible_org_codes(
        caller_org_code(payload), role, tenant_id=tenant_id
    )
    enriched = enrich_workbench_backlog(view, role, tenant_id=tenant_id, visible_org_codes=visible_org_codes)
    enriched["greeting"] = _session_greeting(payload)
    return enriched

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
        # D56 写路径单源：订阅是非三聚合表，下沉 domain repo 方法承担持久化语义，
        # 不再 handler 内自开 SQLAlchemy session 直 commit（绕过写禁区段 25 边界、
        # 与三聚合直写同款 lost-update 隐患）。不存在即 NotFoundError。
        deps.repos.delivery.terminate_subscription(
            subscription_code, reason=reason, actor=actor, audit_id=audit_id
        )
        deps.append_audit_feed("subscription.terminate", subscription_code, "ok", actor)
        return {"subscription_code": subscription_code, "status": "terminated", "audit_id": audit_id}

    return deps.write(ctx, payload, mutation)


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_workbench_view(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _get_workbench(brain, deps, ctx, str(payload.get("role", ctx.role)), payload)

def handler_service_rating_submit(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _submit_service_rating(brain, deps, ctx, payload)

def handler_subscription_terminate(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _terminate_subscription(brain, deps, ctx, payload)

