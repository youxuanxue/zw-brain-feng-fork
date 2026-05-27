"""J2 compliance handlers — 8 cap migrated from BrainService (F1 turn 4).

Method bodies physically migrated; `self.` → `brain.` substitution applied. Per-cap handler
functions registered in `zw_brain.command.dispatch.DISPATCH_TABLE`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass



import copy

import zw_brain.shared.clock as clock
import zw_brain.shared.ids as ids
from zw_brain.command.brain import BrainServiceError, InvalidStateError, NotFoundError
from zw_brain.command.deps import HandlerDeps, SkillContext

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _configure_compliance_rule(brain, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    rule_id = str(payload["rule_id"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        rules = brain._snapshot.setdefault("compliance_rules", [])
        rule = next((item for item in rules if item.get("id") == rule_id), None)
        rule_payload = {
            "id": rule_id,
            "title": str(payload.get("title", rule_id)),
            "status": str(payload.get("status", "active")),
            "severity": str(payload.get("severity", "mid")),
            "rule_json": brain._safe_json(payload.get("rule_json") or {}),
            "updatedAt": clock.now_datetime(),
        }
        if rule is None:
            rules.append(rule_payload)
        else:
            rule.update(rule_payload)
        brain._append_audit_feed("compliance.rule.configure", rule_id, "ok", actor)
        return {"rule_id": rule_id, "status": rule_payload["status"], "audit_id": audit_id}

    return brain._mutate("compliance.rule.configure", role, confirmed, payload, mutation)

def _open_compliance_case(brain, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    case_id = str(payload.get("case_id") or payload.get("dispute_id") or f"CMP-{ids.new_audit_id()}")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        cases = brain._snapshot.setdefault("disputes", [])
        if any(item.get("id") == case_id for item in cases):
            raise InvalidStateError("compliance case already exists")
        cases.append(
            {
                "id": case_id,
                "title": str(payload.get("title", case_id)),
                "severity": str(payload.get("severity", "mid")),
                "status": "detected",
                "owner": str(payload.get("owner", payload.get("owner_org_id", "合规治理组"))),
                "timeline": [
                    {
                        "time": clock.now_datetime(),
                        "label": "打开合规事件",
                        "note": str(payload.get("summary", payload.get("note", "已登记合规信号并进入最小闭环。"))),
                    }
                ],
                "aiSummary": str(payload.get("aiSummary", payload.get("summary", "合规事件已进入 zw-brain 最小闭环，后续只沉淀证据与处置结果。"))),
            }
        )
        brain._append_audit_feed("compliance.case.open", case_id, "ok", actor)
        return {"case_id": case_id, "status": "detected", "audit_id": audit_id}

    return brain._mutate("compliance.case.open", role, confirmed, payload | {"case_id": case_id}, mutation)

def _transition_compliance_case(brain, case_id: str, status: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    case = next((item for item in brain._snapshot.setdefault("disputes", []) if item.get("id") == case_id), None)
    if case is None:
        raise NotFoundError(case_id)
    allowed = {
        "detected": {"assigned", "resolved"},
        "open": {"assigned", "resolved"},
        "assigned": {"resolved"},
        "escalated": {"assigned", "resolved"},
        "resolved": {"closed"},
        "closed": set(),
    }
    if status not in allowed.get(str(case.get("status", "open")), set()):
        raise InvalidStateError(f"invalid compliance transition: {case.get('status')} -> {status}")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        case["status"] = status
        if payload.get("owner") or payload.get("owner_org_id"):
            case["owner"] = str(payload.get("owner", payload.get("owner_org_id")))
        label = {"assign": "分派合规处置", "resolve": "完成合规处置", "close": "关闭合规事件"}[action]
        case.setdefault("timeline", []).append({"time": clock.now_datetime(), "label": label, "note": str(payload.get("opinion", payload.get("summary", label)))})
        case["aiSummary"] = str(payload.get("aiSummary", payload.get("summary", f"合规事件已{label}，证据链保留在统一审计与快照中。")))
        brain._append_audit_feed(f"compliance.case.{action}", case_id, "ok", actor)
        return {"case_id": case_id, "status": case["status"], "audit_id": audit_id}

    return brain._mutate(f"compliance.case.{action}", role, confirmed, {"case_id": case_id, "status": status} | payload, mutation)

def _query_compliance_cases(brain, *, status: Any = None, severity: Any = None) -> dict[str, Any]:
    cases = copy.deepcopy(brain._snapshot.get("disputes", []))
    if status:
        cases = [item for item in cases if item.get("status") == str(status)]
    if severity:
        cases = [item for item in cases if item.get("severity") == str(severity)]
    return {"items": cases, "total": len(cases)}

def _query_compliance_metrics(brain) -> dict[str, Any]:
    cases = brain._snapshot.get("disputes", [])
    by_status: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for item in cases:
        by_status[str(item.get("status", "unknown"))] = by_status.get(str(item.get("status", "unknown")), 0) + 1
        by_severity[str(item.get("severity", "unknown"))] = by_severity.get(str(item.get("severity", "unknown")), 0) + 1
    open_count = sum(count for status, count in by_status.items() if status not in {"resolved", "closed"})
    return {"total": len(cases), "open_count": open_count, "resolved_count": by_status.get("resolved", 0) + by_status.get("closed", 0), "by_status": by_status, "by_severity": by_severity}

def _investigate_dispute(brain, dispute_id: str, action: str, role: str, confirmed: bool) -> dict[str, Any]:
    dispute = next((item for item in brain._snapshot["disputes"] if item["id"] == dispute_id), None)
    if dispute is None:
        raise NotFoundError(dispute_id)
    if action not in {"progress", "escalate"}:
        raise BrainServiceError(f"unsupported dispute action: {action}")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        if action == "progress":
            dispute["timeline"].append(
                {
                    "time": clock.now_datetime(),
                    "label": "推进调查",
                    "note": "已补充核查当前绕行与责任链证据，等待进一步治理决定。",
                }
            )
            dispute["aiSummary"] = "调查已推进：当前已补充责任链与证据核查，下一步判断是否需要升级到模板或制度治理。"
            brain._set_todo_status("ROLE_SECURITY_AUDIT", dispute_id, "处理中")
            brain._set_todo_status("ROLE_ORGAN_MANAGER", dispute_id, "待核查")
            event_type = "compliance.investigate-case"
        else:
            dispute["status"] = "escalated"
            dispute["owner"] = "区台账治理组"
            dispute["timeline"].append(
                {
                    "time": clock.now_datetime(),
                    "label": "升级治理",
                    "note": "已升级到模板治理与制度治理联动处置，要求供给侧与减负治理协同收口。",
                }
            )
            dispute["aiSummary"] = "争议已升级：当前不再停留在个案调查，而是转入模板治理与制度治理联动处置。"
            brain._set_todo_status("ROLE_SECURITY_AUDIT", dispute_id, "已升级")
            brain._set_todo_status("ROLE_ORGAN_MANAGER", dispute_id, "已升级")
            event_type = "compliance.escalate-case"
        brain._append_audit_feed(event_type, dispute_id, "ok", actor)
        return {"dispute_id": dispute_id, "status": dispute["status"], "action": action}

    return brain._mutate("compliance.investigate_case", role, confirmed, {"dispute_id": dispute_id, "action": action}, mutation)


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_compliance_case_open(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _open_compliance_case(brain, payload)

def handler_compliance_case_assign(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _transition_compliance_case(brain, str(payload["case_id"]), "assigned", "assign", payload)

def handler_compliance_case_close(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _transition_compliance_case(brain, str(payload["case_id"]), "closed", "close", payload)

def handler_compliance_case_resolve(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _transition_compliance_case(brain, str(payload["case_id"]), "resolved", "resolve", payload)

def handler_compliance_case_query(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _query_compliance_cases(brain, status=payload.get("status"), severity=payload.get("severity"))

def handler_compliance_metric_query(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _query_compliance_metrics(brain)

def handler_compliance_rule_configure(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _configure_compliance_rule(brain, payload)

def handler_compliance_investigate_case(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _investigate_dispute(brain, str(payload["dispute_id"]), str(payload["action"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))

