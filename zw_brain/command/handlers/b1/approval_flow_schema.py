"""B1 approval_flow_schema handlers — E3 Wave-2 三引擎 F1/F3。

F1：approval_flow.schema.commit（preview → live）。
F3：approval_flow.nl_draft（一句话生成 draft）
    + approval_flow.schema.promote_to_preview（draft → preview）
    + approval_flow.schema.revert_to_draft（preview → draft）。

handler 签名：def handler(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService

from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.domain.approval_flow_nl_draft import (
    ApprovalFlowDraftSourceError,
    generate_draft,
)
from zw_brain.domain.approval_flow_schema import (
    ApprovalFlowSchemaRepo,
    ApprovalFlowTransitionError,
)
from zw_brain.shared.db import create_session_factory


def _commit_schema(brain, deps, ctx: BrainService, skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    tenant_id = str(payload.get("tenant_id") or "")
    schema_id = str(payload.get("schema_id") or "")
    if not tenant_id or not schema_id:
        raise ValueError("tenant_id and schema_id are required")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            repo = ApprovalFlowSchemaRepo(session)
            record = repo.get(schema_id)
            if record.tenant_id != tenant_id:
                raise ApprovalFlowTransitionError(
                    f"schema {schema_id!r} does not belong to tenant {tenant_id!r}"
                )
            committed = repo.commit_to_live(schema_id)
            deps.append_audit_feed(skill_id, schema_id, "ok", actor)
            return {
                "schema_id": committed.id,
                "schema_code": committed.schema_code,
                "version": committed.version,
                "committed_at": committed.committed_at.isoformat() if committed.committed_at else None,
            }

    return deps.write(ctx, payload, mutation)


def _nl_draft(brain, deps, ctx: BrainService, skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed", True))  # manifest 不要求 human confirm，默认通过
    tenant_id = str(payload.get("tenant_id") or "")
    schema_code = str(payload.get("schema_code") or "")
    title = str(payload.get("title") or "")
    intent_text = str(payload.get("intent_text") or "")
    created_by = str(payload.get("created_by") or "")
    deterministic_only = bool(payload.get("deterministic_only", False))
    if not (tenant_id and schema_code and title and intent_text and created_by):
        raise ApprovalFlowDraftSourceError(
            "tenant_id / schema_code / title / intent_text / created_by are required"
        )

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            repo = ApprovalFlowSchemaRepo(session)
            record, source_meta = generate_draft(
                repo,
                tenant_id=tenant_id,
                schema_code=schema_code,
                title=title,
                intent_text=intent_text,
                created_by=created_by,
                deterministic_only=deterministic_only,
                request_id=audit_id,
            )
            payload_summary = {
                "node_count": len(record.payload_json.get("nodes", [])),
                "selection_rule_count": len(record.payload_json.get("selection_rules", [])),
                "branch_count": len(record.payload_json.get("branches", [])),
            }
            deps.append_audit_feed(skill_id, record.id, "ok", actor)
            return {
                "schema_id": record.id,
                "status": record.status,
                "source_kind": record.source_kind,
                "draft_source_text": record.draft_source_text,
                "payload_summary": payload_summary,
                "source_metadata": source_meta,
            }

    return deps.write(ctx, payload, mutation)


def _promote_to_preview(brain, deps, ctx: BrainService, skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    tenant_id = str(payload.get("tenant_id") or "")
    schema_id = str(payload.get("schema_id") or "")
    if not tenant_id or not schema_id:
        raise ValueError("tenant_id and schema_id are required")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            repo = ApprovalFlowSchemaRepo(session)
            record = repo.get(schema_id)
            if record.tenant_id != tenant_id:
                raise ApprovalFlowTransitionError(
                    f"schema {schema_id!r} does not belong to tenant {tenant_id!r}"
                )
            promoted = repo.promote_to_preview(schema_id)
            deps.append_audit_feed(skill_id, schema_id, "ok", actor)
            return {
                "schema_id": promoted.id,
                "status": promoted.status,
                "version": promoted.version,
            }

    return deps.write(ctx, payload, mutation)


def _revert_to_draft(brain, deps, ctx: BrainService, skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    tenant_id = str(payload.get("tenant_id") or "")
    schema_id = str(payload.get("schema_id") or "")
    if not tenant_id or not schema_id:
        raise ValueError("tenant_id and schema_id are required")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            repo = ApprovalFlowSchemaRepo(session)
            record = repo.get(schema_id)
            if record.tenant_id != tenant_id:
                raise ApprovalFlowTransitionError(
                    f"schema {schema_id!r} does not belong to tenant {tenant_id!r}"
                )
            reverted = repo.revert_to_draft(schema_id)
            deps.append_audit_feed(skill_id, schema_id, "ok", actor)
            return {
                "schema_id": reverted.id,
                "status": reverted.status,
                "version": reverted.version,
            }

    return deps.write(ctx, payload, mutation)


def handler_approval_flow_schema_commit(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _commit_schema(brain, deps, ctx, skill_id, payload)


def handler_approval_flow_nl_draft(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _nl_draft(brain, deps, ctx, skill_id, payload)


def handler_approval_flow_schema_promote_to_preview(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _promote_to_preview(brain, deps, ctx, skill_id, payload)


def handler_approval_flow_schema_revert_to_draft(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _revert_to_draft(brain, deps, ctx, skill_id, payload)
