"""J1 recommendation_suggest handler — E3 Wave-2 三引擎 F6。

承接 recommendation.similar_catalog.suggest cap：read-normal，
基于 live 规则 + 历史投影对意向文本做相似目录推荐；推荐为空且
fallback_register=true 时落 manual_requirement 转人工登记。

非 mutation 路径（无 db_write 主分支），但 audit 仍发；fallback 时 db_write 局部发生。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService

import zw_brain.shared.ids as ids
from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.domain.recommendation_engine import RecommendationEngine
from zw_brain.shared.db import create_session_factory


def _suggest(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    tenant_id = str(payload.get("tenant_id") or "")
    intent_text = str(payload.get("intent_text") or "")
    submitted_by = str(payload.get("submitted_by") or "")
    if not tenant_id or not intent_text or not submitted_by:
        raise ValueError("tenant_id, intent_text and submitted_by are required")
    intent_org = payload.get("intent_org")
    top_k = int(payload.get("top_k") or 5)
    fallback_register = bool(payload.get("fallback_register"))

    SessionLocal = create_session_factory()
    with SessionLocal() as session:
        engine = RecommendationEngine(session)
        candidates = engine.suggest(
            tenant_id=tenant_id,
            intent_text=intent_text,
            intent_org=intent_org if isinstance(intent_org, str) else None,
            top_k=top_k,
        )
        candidate_dicts = [c.to_dict() for c in candidates]
        manual_submission_id: str | None = None
        fallback_required = not candidates
        if fallback_required and fallback_register:
            record = engine.register_manual_requirement(
                tenant_id=tenant_id,
                submitted_by=submitted_by,
                intent_text=intent_text,
            )
            manual_submission_id = record.id

    return {
        "ok": True,
        "skill_id": skill_id,
        "audit_id": ids.new_audit_id(),
        "result": {
            "candidates": candidate_dicts,
            "fallback_required": fallback_required,
            "manual_submission_id": manual_submission_id,
        },
    }


def handler_recommendation_similar_catalog_suggest(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _suggest(brain, skill_id, payload)
