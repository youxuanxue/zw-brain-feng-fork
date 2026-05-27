"""J1 application_grant handlers — 4 cap migrated from BrainService (F1 turn 6, J1 收官)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService

import zw_brain.shared.clock as clock
from zw_brain.command.brain import BrainServiceError

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _approve_application_grant(brain, payload: dict[str, Any]) -> dict[str, Any]:
    decision = str(payload["decision"])
    if decision == "approve":
        return brain.grant_delivery_access(str(payload["task_id"]), str(payload.get("role", brain._ui_state["role"])), bool(payload.get("confirmed")))
    if decision in {"reject", "return_for_fix"}:
        task_id = str(payload["task_id"])
        role = str(payload.get("role", brain._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            task = brain._delivery_by_id(task_id)
            task["status"] = "warning"
            task["updatedAt"] = clock.now_datetime()
            task["note"] = str(payload.get("reason", "授权申请未通过。"))
            task.setdefault("history", []).append({"time": clock.now_short_time(), "state": "授权未通过", "detail": task["note"]})
            brain._append_audit_feed("application.grant.approve", task_id, "warning", actor)
            return {"task_id": task_id, "decision": decision, "status": task["status"], "audit_id": audit_id}

        return brain._mutate("application.grant.approve", role, confirmed, payload, mutation)
    raise BrainServiceError(f"unsupported grant decision: {decision}")

def _renew_application_grant(brain, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    # Customer surface forwards `delivery_task_id`; the legacy contract used
    # `task_id`. Accept either so the same skill works from both call sites.
    task_id = str(payload.get("task_id") or payload.get("delivery_task_id"))

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        task = brain._delivery_by_id(task_id)
        task.setdefault("access", {})["renew_until"] = payload.get("renew_until")
        task["updatedAt"] = clock.now_datetime()
        task.setdefault("history", []).append({"time": clock.now_short_time(), "state": "授权已续期", "detail": str(payload.get("reason", "访问授权续期完成。"))})
        brain._delivery_repo().add_execution_evidence({"evidence_ref": audit_id, "delivery_code": task_id, "executor_kind": "grant_policy", "evidence_kind": "grant_renewal", "result_status": "renewed", "payload_json": payload})
        brain._append_audit_feed("application.grant.renew", task_id, "ok", actor)
        return {"task_id": task_id, "renew_until": payload.get("renew_until"), "audit_id": audit_id}

    return brain._mutate("application.grant.renew", role, confirmed, payload, mutation)

def _suspend_application_grant(brain, payload: dict[str, Any]) -> dict[str, Any]:
    """审批人 暂停已生效的授权 — 申请人 暂时无法访问但授权不失效，可恢复。"""
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    request_id = str(payload.get("request_id") or payload.get("delivery_task_id") or "")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        request = brain._request_by_id(request_id) if request_id.startswith("REQ-") else None
        if request is not None:
            request.setdefault("grant", {})["suspended"] = True
            request.setdefault("timeline", []).append({"label": "授权已暂停", "time": clock.now_datetime(), "note": str(payload.get("reason", "审批人 临时暂停以核实使用边界。"))})
        brain._append_audit_feed("application.grant.suspend", request_id, "ok", actor)
        return {"request_id": request_id, "suspended": True, "audit_id": audit_id}

    return brain._mutate("application.grant.suspend", role, confirmed, payload, mutation)

def _revoke_application_grant(brain, payload: dict[str, Any]) -> dict[str, Any]:
    """审批人 收回已生效的授权 — 永久收回，申请人 需重新申请。"""
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    request_id = str(payload.get("request_id") or payload.get("delivery_task_id") or "")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        request = brain._request_by_id(request_id) if request_id.startswith("REQ-") else None
        if request is not None:
            request.setdefault("grant", {})["revoked"] = True
            request["status"] = "revoked"
            request.setdefault("timeline", []).append({"label": "授权已收回", "time": clock.now_datetime(), "note": str(payload.get("reason", "审批人 收回授权，需重新申请。"))})
        brain._append_audit_feed("application.grant.revoke", request_id, "ok", actor)
        return {"request_id": request_id, "revoked": True, "audit_id": audit_id}

    return brain._mutate("application.grant.revoke", role, confirmed, payload, mutation)


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_application_grant_approve(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _approve_application_grant(brain, payload)

def handler_application_grant_renew(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _renew_application_grant(brain, payload)

def handler_application_grant_suspend(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _suspend_application_grant(brain, payload)

def handler_application_grant_revoke(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _revoke_application_grant(brain, payload)

