"""J1 governance_dispute handlers — 2 cap migrated from BrainService (F1 turn 6, J1 收官)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

import copy

from zw_brain.command.brain import _DEFAULT_TENANT_ID, NotFoundError
from zw_brain.command.deps import HandlerDeps, SkillContext

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _list_governance_disputes(brain, deps, ctx) -> dict[str, Any]:
    items = copy.deepcopy(brain._snapshot["disputes"])
    store = brain._state_store.database_store
    if store is not None:
        all_records = store.objection_repo.list_cases(tenant_id=_DEFAULT_TENANT_ID)
        records = {record.id: record for record in all_records}
        seed_ids = {item["id"] for item in items}
        for item in items:
            record = records.get(item["id"])
            if record is not None:
                item["repository"] = {
                    "objectionKind": record.objection_kind,
                    "targetType": record.target_type,
                    "status": record.status,
                }
                evaluation = store.objection_repo.get_evaluation(item["id"])
                if evaluation is not None:
                    item["evaluation"] = {
                        "solvedFlag": evaluation.solved_flag,
                        "overallScore": evaluation.overall_score,
                        "comment": evaluation.comment,
                    }
        # Surface objection cases created at runtime (not present in the
        # seed disputes list) so newly-filed customer objections show up in
        # the governance dashboard the same turn.
        for record in all_records:
            if record.id in seed_ids:
                continue
            items.append({
                "id": record.id,
                "topic": record.title,
                "type": record.objection_kind,
                "status": record.status,
                "targetType": record.target_type,
                "targetId": record.target_id,
                "createdAt": record.created_at.isoformat() if getattr(record, "created_at", None) else "",
                "repository": {
                    "objectionKind": record.objection_kind,
                    "targetType": record.target_type,
                    "status": record.status,
                },
            })
    return {
        "items": items,
        "alerts": copy.deepcopy(brain._snapshot["alerts"]),
        "tickets": copy.deepcopy(brain._snapshot["tickets"]),
        "knowledgeArticles": copy.deepcopy(brain._snapshot["knowledge_articles"]),
    }

def _get_dispute(brain, deps, ctx, dispute_id: str) -> dict[str, Any]:
    dispute = next((copy.deepcopy(item) for item in brain._snapshot["disputes"] if item["id"] == dispute_id), None)
    if dispute is None:
        raise NotFoundError(dispute_id)
    store = brain._state_store.database_store
    if store is None:
        return dispute
    record = store.objection_repo.get_case(dispute_id)
    if record is None:
        return dispute
    dispute["repository"] = {
        "objectionKind": record.objection_kind,
        "targetType": record.target_type,
        "status": record.status,
    }
    dispute["process"] = [
        {
            "nodeName": item.node_name,
            "actionType": item.action_type,
            "actionResult": item.action_result,
            "opinion": item.opinion,
        }
        for item in store.objection_repo.list_processes(dispute_id)
    ]
    evaluation = store.objection_repo.get_evaluation(dispute_id)
    if evaluation is not None:
        dispute["evaluation"] = {
            "solvedFlag": evaluation.solved_flag,
            "overallScore": evaluation.overall_score,
            "comment": evaluation.comment,
        }
    return dispute


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_governance_dispute_list(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _list_governance_disputes(brain, deps, ctx)

def handler_governance_dispute_view(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _get_dispute(brain, deps, ctx, str(payload["dispute_id"]))

