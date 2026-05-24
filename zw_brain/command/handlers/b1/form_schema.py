"""B1 form_schema handlers — E3 Wave-2 三引擎 F4/F5。

F4：form_schema.commit（preview → live）。
F5：form_schema.nl_draft（一句话生成 draft）
    + form_schema.promote_to_preview（draft → preview）
    + form_schema.revert_to_draft（preview → draft）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService

from zw_brain.domain.form_schema import FormSchemaRepo, FormSchemaTransitionError
from zw_brain.domain.form_schema_nl_draft import FormSchemaDraftSourceError, generate_draft
from zw_brain.shared.db import create_session_factory


def _commit_schema(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    tenant_id = str(payload.get("tenant_id") or "")
    schema_id = str(payload.get("schema_id") or "")
    if not tenant_id or not schema_id:
        raise ValueError("tenant_id and schema_id are required")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            repo = FormSchemaRepo(session)
            record = repo.get(schema_id)
            if record.tenant_id != tenant_id:
                raise FormSchemaTransitionError(
                    f"form schema {schema_id!r} does not belong to tenant {tenant_id!r}"
                )
            committed = repo.commit_to_live(schema_id)
            brain._append_audit_feed(skill_id, schema_id, "ok", actor)
            return {
                "schema_id": committed.id,
                "form_code": committed.form_code,
                "version": committed.version,
                "committed_at": committed.committed_at.isoformat() if committed.committed_at else None,
            }

    return brain._mutate(skill_id, role, confirmed, payload, mutation)


def _nl_draft(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed", True))
    tenant_id = str(payload.get("tenant_id") or "")
    form_code = str(payload.get("form_code") or "")
    title = str(payload.get("title") or "")
    intent_text = str(payload.get("intent_text") or "")
    created_by = str(payload.get("created_by") or "")
    deterministic_only = bool(payload.get("deterministic_only", False))
    if not (tenant_id and form_code and title and intent_text and created_by):
        raise FormSchemaDraftSourceError(
            "tenant_id / form_code / title / intent_text / created_by are required"
        )

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            repo = FormSchemaRepo(session)
            record, source_meta = generate_draft(
                repo,
                tenant_id=tenant_id,
                form_code=form_code,
                title=title,
                intent_text=intent_text,
                created_by=created_by,
                deterministic_only=deterministic_only,
                request_id=audit_id,
            )
            payload_summary = {
                "section_count": len(record.payload_json.get("sections", [])),
                "field_count": len(record.payload_json.get("fields", [])),
                "validator_count": len(record.payload_json.get("validators", [])),
            }
            brain._append_audit_feed(skill_id, record.id, "ok", actor)
            return {
                "schema_id": record.id,
                "status": record.status,
                "source_kind": record.source_kind,
                "draft_source_text": record.draft_source_text,
                "payload_summary": payload_summary,
                "source_metadata": source_meta,
            }

    return brain._mutate(skill_id, role, confirmed, payload, mutation)


def _promote_to_preview(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    tenant_id = str(payload.get("tenant_id") or "")
    schema_id = str(payload.get("schema_id") or "")
    if not tenant_id or not schema_id:
        raise ValueError("tenant_id and schema_id are required")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            repo = FormSchemaRepo(session)
            record = repo.get(schema_id)
            if record.tenant_id != tenant_id:
                raise FormSchemaTransitionError(
                    f"form schema {schema_id!r} does not belong to tenant {tenant_id!r}"
                )
            promoted = repo.promote_to_preview(schema_id)
            brain._append_audit_feed(skill_id, schema_id, "ok", actor)
            return {
                "schema_id": promoted.id,
                "status": promoted.status,
                "version": promoted.version,
            }

    return brain._mutate(skill_id, role, confirmed, payload, mutation)


def _revert_to_draft(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    tenant_id = str(payload.get("tenant_id") or "")
    schema_id = str(payload.get("schema_id") or "")
    if not tenant_id or not schema_id:
        raise ValueError("tenant_id and schema_id are required")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            repo = FormSchemaRepo(session)
            record = repo.get(schema_id)
            if record.tenant_id != tenant_id:
                raise FormSchemaTransitionError(
                    f"form schema {schema_id!r} does not belong to tenant {tenant_id!r}"
                )
            reverted = repo.revert_to_draft(schema_id)
            brain._append_audit_feed(skill_id, schema_id, "ok", actor)
            return {
                "schema_id": reverted.id,
                "status": reverted.status,
                "version": reverted.version,
            }

    return brain._mutate(skill_id, role, confirmed, payload, mutation)


def handler_form_schema_commit(
    brain: BrainService, skill_id: str, payload: dict[str, Any]
) -> Any:
    return _commit_schema(brain, skill_id, payload)


def handler_form_schema_nl_draft(
    brain: BrainService, skill_id: str, payload: dict[str, Any]
) -> Any:
    return _nl_draft(brain, skill_id, payload)


def handler_form_schema_promote_to_preview(
    brain: BrainService, skill_id: str, payload: dict[str, Any]
) -> Any:
    return _promote_to_preview(brain, skill_id, payload)


def handler_form_schema_revert_to_draft(
    brain: BrainService, skill_id: str, payload: dict[str, Any]
) -> Any:
    return _revert_to_draft(brain, skill_id, payload)
