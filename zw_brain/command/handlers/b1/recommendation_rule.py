"""B1 recommendation_rule handlers — E3 Wave-2 三引擎 F6。

承接 recommendation.rule.commit cap：管理员把项目级推荐规则从 preview 态确认入库
（version+1，进入 live），落 audit_event 走 BrainService._mutate hook。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService

from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.domain.recommendation_rule import (
    RecommendationRuleRepo,
    RecommendationRuleTransitionError,
)
from zw_brain.shared.db import create_session_factory


def _commit_rule(brain, deps, ctx: BrainService, skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    tenant_id = str(payload.get("tenant_id") or "")
    rule_id = str(payload.get("rule_id") or "")
    rule_code = str(payload.get("rule_code") or "")
    if not tenant_id:
        raise ValueError("tenant_id is required")
    if not rule_id and not rule_code:
        raise ValueError("either rule_id or rule_code is required")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            repo = RecommendationRuleRepo(session)
            target_id = rule_id
            if not target_id:
                # 推荐规则按设计无独立 NL draft 步骤：UI 点「入库生效」时按
                # (tenant, rule_code) 复用最新 record 的 payload 自动 create_draft
                # → promote_to_preview → commit_to_live，自增 version 不撞 UNIQUE。
                # 若 (tenant, rule_code) 无现存记录，明确拒绝——不允许自动 seed
                # 假业务数据（违反 D11）；客户场景下首条规则必须通过 fixture /
                # acceptance test / admin API 显式创建后再通过 UI commit。
                latest = repo.latest_by_code(tenant_id, rule_code)
                if latest is None:
                    raise RecommendationRuleTransitionError(
                        f"no existing recommendation rule for code {rule_code!r} in tenant "
                        f"{tenant_id!r}; create the first draft via fixture or admin API "
                        f"before invoking commit from UI"
                    )
                draft = repo.create_draft(
                    tenant_id=tenant_id,
                    rule_code=rule_code,
                    title=str(payload.get("title") or latest.title),
                    payload=latest.payload_json,
                    source_kind="reapply",
                    draft_source_text=str(
                        payload.get("draft_source_text") or (latest.draft_source_text or "")
                    ) or None,
                    created_by=actor,
                )
                repo.promote_to_preview(draft.id)
                target_id = draft.id
            else:
                record = repo.get(target_id)
                if record.tenant_id != tenant_id:
                    raise RecommendationRuleTransitionError(
                        f"recommendation rule {target_id!r} does not belong to tenant {tenant_id!r}"
                    )
            committed = repo.commit_to_live(target_id)
            deps.append_audit_feed(skill_id, target_id, "ok", actor)
            return {
                "rule_id": committed.id,
                "rule_code": committed.rule_code,
                "version": committed.version,
                "committed_at": committed.committed_at.isoformat() if committed.committed_at else None,
            }

    return deps.write(ctx, payload, mutation)


def handler_recommendation_rule_commit(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _commit_rule(brain, deps, ctx, skill_id, payload)
