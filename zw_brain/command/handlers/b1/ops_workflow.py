"""B1 ops_workflow handlers — 3 cap migrated from BrainService (F1 turn 5).

Method bodies physically migrated (`self.` → `brain.`); per-cap handler functions
registered in `zw_brain.command.dispatch.DISPATCH_TABLE`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService




import zw_brain.shared.clock as clock

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _create_ops_ticket(brain, payload: dict[str, Any]) -> dict[str, Any]:
    """安全审计员 创建运维工单（告警处理 / 巡检 / 拨测 / 安全 / 其他）。"""
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    ticket_type = str(payload.get("ticket_type", "alert"))
    title = str(payload.get("title", "")).strip() or "运维工单"
    assignee = str(payload.get("assignee", "")).strip() or "未指派"

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        ticket_id = f"TK-{clock.now_date()}-{len(brain._snapshot.get('tickets', [])) + 1:03d}"
        ticket = {
            "id": ticket_id,
            "type": ticket_type,
            "title": title,
            "assignee": assignee,
            "status": "处理中",
            "createdBy": actor,
            "createdAt": clock.now_datetime(),
        }
        brain._snapshot.setdefault("tickets", []).insert(0, ticket)
        brain._append_audit_feed("ops.ticket.create", ticket_id, "ok", actor)
        return {"ticket": ticket, "audit_id": audit_id}

    return brain._mutate("ops.ticket.create", role, confirmed, payload, mutation)

def _close_ops_ticket(brain, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    ticket_id = str(payload.get("ticket_id", "")).strip()

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        tickets = brain._snapshot.get("tickets", [])
        target = next((t for t in tickets if t.get("id") == ticket_id), None)
        if target is not None:
            target["status"] = "已关闭"
            target["closedBy"] = actor
            target["closedAt"] = clock.now_datetime()
        brain._append_audit_feed("ops.ticket.close", ticket_id, "ok", actor)
        return {"ticket_id": ticket_id, "audit_id": audit_id}

    return brain._mutate("ops.ticket.close", role, confirmed, payload, mutation)

def _submit_shift_handover(brain, payload: dict[str, Any]) -> dict[str, Any]:
    """安全审计员 交接班 — 记录本班通报事项 + 待跟进工单 + 接班人。"""
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    summary = str(payload.get("summary", "")).strip()
    pending = payload.get("pending_tickets") or []
    next_shift = str(payload.get("next_shift_assignee", "")).strip() or "下班次值班人"

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        handover = {
            "id": f"SH-{clock.now_date()}-{len(brain._snapshot.get('shift_handovers', [])) + 1:03d}",
            "summary": summary,
            "pendingTickets": pending,
            "nextShiftAssignee": next_shift,
            "submittedBy": actor,
            "submittedAt": clock.now_datetime(),
        }
        brain._snapshot.setdefault("shift_handovers", []).insert(0, handover)
        brain._append_audit_feed("ops.shift_handover.submit", handover["id"], "ok", actor)
        return {"handover": handover, "audit_id": audit_id}

    return brain._mutate("ops.shift_handover.submit", role, confirmed, payload, mutation)


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_ops_ticket_create(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _create_ops_ticket(brain, payload)

def handler_ops_ticket_close(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _close_ops_ticket(brain, payload)

def handler_ops_shift_handover_submit(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _submit_shift_handover(brain, payload)

