"""B1 recommendation_rule handlers — E3 Wave-2 三引擎 F6。

承接 recommendation.rule.commit cap：管理员把项目级推荐规则从 preview 态确认入库
（version+1，进入 live），落 audit_event 走 BrainService._mutate hook。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService

from zw_brain.domain.recommendation_rule import (
    RecommendationRuleRepo,
    RecommendationRuleTransitionError,
)
from zw_brain.shared.db import create_session_factory


def _commit_rule(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    tenant_id = str(payload.get("tenant_id") or "")
    rule_id = str(payload.get("rule_id") or "")
    if not tenant_id or not rule_id:
        raise ValueError("tenant_id and rule_id are required")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            repo = RecommendationRuleRepo(session)
            record = repo.get(rule_id)
            if record.tenant_id != tenant_id:
                raise RecommendationRuleTransitionError(
                    f"recommendation rule {rule_id!r} does not belong to tenant {tenant_id!r}"
                )
            committed = repo.commit_to_live(rule_id)
            brain._append_audit_feed(skill_id, rule_id, "ok", actor)
            return {
                "rule_id": committed.id,
                "rule_code": committed.rule_code,
                "version": committed.version,
                "committed_at": committed.committed_at.isoformat() if committed.committed_at else None,
            }

    return brain._mutate(skill_id, role, confirmed, payload, mutation)


def handler_recommendation_rule_commit(
    brain: BrainService, skill_id: str, payload: dict[str, Any]
) -> Any:
    return _commit_rule(brain, skill_id, payload)
