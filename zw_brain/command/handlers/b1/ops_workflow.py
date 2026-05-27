"""B1 ops_workflow handlers — 3 cap migrated from BrainService (F1 turn 5).

Method bodies physically migrated (`self.` → `brain.`); per-cap handler functions
registered in `zw_brain.command.dispatch.DISPATCH_TABLE`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass




import zw_brain.shared.clock as clock
from zw_brain.command.deps import HandlerDeps, SkillContext

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _create_ops_ticket(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    """安全审计员 创建运维工单（告警处理 / 巡检 / 拨测 / 安全 / 其他）。"""
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    ticket_type = str(payload.get("ticket_type", "alert"))
    title = str(payload.get("title", "")).strip() or "运维工单"
    assignee = str(payload.get("assignee", "")).strip() or "未指派"

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        ticket_id = f"TK-{clock.now_date()}-{len(deps.brain_legacy._snapshot.get('tickets', [])) + 1:03d}"
        ticket = {
            "id": ticket_id,
            "type": ticket_type,
            "title": title,
            "assignee": assignee,
            "status": "处理中",
            "createdBy": actor,
            "createdAt": clock.now_datetime(),
        }
        deps.brain_legacy._snapshot.setdefault("tickets", []).insert(0, ticket)
        deps.append_audit_feed("ops.ticket.create", ticket_id, "ok", actor)
        return {"ticket": ticket, "audit_id": audit_id}

    return deps.write(ctx, payload, mutation)

def _close_ops_ticket(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    ticket_id = str(payload.get("ticket_id", "")).strip()

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        tickets = deps.brain_legacy._snapshot.get("tickets", [])
        target = next((t for t in tickets if t.get("id") == ticket_id), None)
        if target is not None:
            target["status"] = "已关闭"
            target["closedBy"] = actor
            target["closedAt"] = clock.now_datetime()
        deps.append_audit_feed("ops.ticket.close", ticket_id, "ok", actor)
        return {"ticket_id": ticket_id, "audit_id": audit_id}

    return deps.write(ctx, payload, mutation)

def _submit_shift_handover(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    """安全审计员 交接班 — 记录本班通报事项 + 待跟进工单 + 接班人。"""
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    summary = str(payload.get("summary", "")).strip()
    pending = payload.get("pending_tickets") or []
    next_shift = str(payload.get("next_shift_assignee", "")).strip() or "下班次值班人"

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        handover = {
            "id": f"SH-{clock.now_date()}-{len(deps.brain_legacy._snapshot.get('shift_handovers', [])) + 1:03d}",
            "summary": summary,
            "pendingTickets": pending,
            "nextShiftAssignee": next_shift,
            "submittedBy": actor,
            "submittedAt": clock.now_datetime(),
        }
        deps.brain_legacy._snapshot.setdefault("shift_handovers", []).insert(0, handover)
        deps.append_audit_feed("ops.shift_handover.submit", handover["id"], "ok", actor)
        return {"handover": handover, "audit_id": audit_id}

    return deps.write(ctx, payload, mutation)


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_ops_ticket_create(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _create_ops_ticket(brain, deps, ctx, payload)

def handler_ops_ticket_close(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _close_ops_ticket(brain, deps, ctx, payload)

def handler_ops_shift_handover_submit(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _submit_shift_handover(brain, deps, ctx, payload)

