"""J1 catalog_entry handlers — 12 cap migrated from BrainService (F1 turn 6, J1 收官)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService

import copy

from zw_brain.command.brain import BrainServiceError, InvalidStateError, NotFoundError
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEFAULT_TENANT_ID = get_runtime_tenant_id()


# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _create_catalog_entry_draft(brain, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    catalog_code = str(payload["catalog_code"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        store = brain._state_store.database_store
        catalog_payload = {
            "id": catalog_code,
            "name": str(payload.get("title", catalog_code)),
            "status": "draft",
            "provider": payload.get("owner_org_id", ""),
            "region_code": payload.get("region_code"),
            "source_ref": payload.get("source_ref"),
            "legacy_object_ref": payload.get("legacy_object_ref") or catalog_code,
            "summary_json": brain._safe_json(payload.get("summary_json") or {}),
        }
        repo = store.catalog_repo if store is not None else CatalogRepository()
        repo.upsert_from_resource(catalog_payload, tenant_id=_DEFAULT_TENANT_ID)
        for item in payload.get("items") or []:
            repo.upsert_item({**item, "catalog_code": catalog_code}, tenant_id=_DEFAULT_TENANT_ID)
        brain._append_audit_feed("catalog.entry.create_draft", catalog_code, "ok", actor)
        return {"catalog_code": catalog_code, "lifecycle_status": "draft", "audit_id": audit_id}

    return brain._mutate("catalog.entry.create_draft", role, confirmed, payload, mutation)

def _transition_catalog_entry(brain, catalog_code: str, status: str, skill_id: str, role: str, confirmed: bool) -> dict[str, Any]:
    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        store = brain._state_store.database_store
        repo = store.catalog_repo if store is not None else CatalogRepository()
        existing = repo.get_entry(catalog_code, tenant_id=_DEFAULT_TENANT_ID)
        if existing is None:
            raise NotFoundError(catalog_code)
        repo.upsert_from_resource(
            {
                **copy.deepcopy(existing.summary_json),
                "id": existing.catalog_code,
                "name": existing.title,
                "status": status,
                "provider": existing.owner_org_id or "",
                "region_code": existing.region_code,
                "source_ref": existing.summary_json.get("source_ref"),
                "legacy_object_ref": existing.catalog_code,
            },
            tenant_id=_DEFAULT_TENANT_ID,
        )
        if status in {"active", "retired"}:
            repo.create_entry_version(
                {
                    "catalog_code": existing.catalog_code,
                    "version_no": f"{status}:{audit_id}",
                    "version_status": status,
                    "snapshot_json": {
                        "catalog_code": existing.catalog_code,
                        "title": existing.title,
                        "lifecycle_status": status,
                        "summary_json": copy.deepcopy(existing.summary_json),
                    },
                    "audit_ref": audit_id,
                    "created_by": actor,
                }
            )
        if store is not None:
            store.approval_repo.upsert_catalog_entry_lifecycle(
                catalog_code,
                status,
                actor=actor,
                skill_id=skill_id,
                audit_id=audit_id,
                decision="return" if status in {"draft", "rejected"} else None,
                tenant_id=_DEFAULT_TENANT_ID,
            )
        brain._append_audit_feed(skill_id, catalog_code, "ok", actor)
        return {"catalog_code": catalog_code, "lifecycle_status": status, "audit_id": audit_id}

    return brain._mutate(skill_id, role, confirmed, {"catalog_code": catalog_code, "status": status}, mutation)

def _query_catalog_entries(
    brain,
    *,
    query: Any = None,
    catalog_code: Any = None,
    source: Any = None,
    lifecycle_status: Any = None,
) -> dict[str, Any]:
    """Query catalog entries with optional structural filters.

    `source` matches `summary_json.source` exactly (e.g. 'reverse' for
    reverse-cataloging drafts). `lifecycle_status` matches the column
    directly. Together they let the 业务运营员 inbox list "pending reverse
    draft" entries without an extra skill.
    """
    store = brain._state_store.database_store
    repo = store.catalog_repo if store is not None else CatalogRepository()
    if query:
        records = repo.search_entries(str(query), tenant_id=_DEFAULT_TENANT_ID)
    else:
        records = repo.list_entries(tenant_id=_DEFAULT_TENANT_ID)
    if lifecycle_status:
        wanted_lc = str(lifecycle_status)
        records = [r for r in records if r.lifecycle_status == wanted_lc]
    if source:
        wanted_src = str(source)
        records = [
            r for r in records
            if isinstance(r.summary_json, dict) and r.summary_json.get("source") == wanted_src
        ]
    entries = [brain._catalog_entry_record_to_dict(item) for item in records]
    if catalog_code:
        entries = [item for item in entries if item["catalog_code"] == str(catalog_code)]
    return {"items": entries, "total": len(entries)}

def _suggest_catalog_entry_reverse_draft(brain, payload: dict[str, Any]) -> dict[str, Any]:
    """Return three-tier field suggestions for a given schema snapshot.

    Read-only. Resolves `schema_ref` against ResourceSchemaSnapshotRecord
    and runs the tiered suggestion logic in `reverse_draft_suggest`.
    """
    from sqlalchemy import select  # noqa: PLC0415

    from zw_brain.command.reverse_draft_suggest import (  # noqa: PLC0415
        build_field_suggestions,
        build_title_suggestion,
    )
    from zw_brain.domain.models import ResourceSchemaSnapshotRecord  # noqa: PLC0415
    from zw_brain.shared.db import create_session_factory  # noqa: PLC0415

    tenant_id = str(payload.get("tenant_id") or _DEFAULT_TENANT_ID)
    schema_ref = str(payload["schema_ref"])
    SessionLocal = create_session_factory()
    with SessionLocal() as session:
        snap = session.execute(
            select(ResourceSchemaSnapshotRecord)
            .where(ResourceSchemaSnapshotRecord.tenant_id == tenant_id)
            .where(ResourceSchemaSnapshotRecord.snapshot_ref == schema_ref)
        ).scalar_one_or_none()
    if snap is None:
        return {
            "schema_ref": schema_ref,
            "title_suggestion": build_title_suggestion(None),
            "fields": [],
            "coverage": {"green": 0, "yellow": 0, "orange": 0, "total": 0},
            "found": False,
        }
    schema_json = snap.schema_json if isinstance(snap.schema_json, dict) else {}
    suggestions, coverage = build_field_suggestions(schema_json)
    title_suggestion = build_title_suggestion(
        schema_json | {"schema_ref": schema_ref, "resource_code": snap.resource_code}
    )
    return {
        "schema_ref": schema_ref,
        "resource_code": snap.resource_code,
        "binding_code": snap.binding_code,
        "title_suggestion": title_suggestion,
        "fields": suggestions,
        "coverage": coverage,
        "found": True,
    }

def _create_catalog_entry_reverse_draft(brain, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    catalog_code = str(payload["catalog_code"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        store = brain._state_store.database_store
        repo = store.catalog_repo if store is not None else CatalogRepository()
        schema_ref = str(payload.get("schema_ref", ""))
        # CatalogRepository.upsert_from_resource stores the whole resource
        # dict as summary_json, so put reverse-draft markers at top level.
        repo.upsert_from_resource(
            {
                "id": catalog_code,
                "name": str(payload.get("title", catalog_code)),
                "status": "draft",
                "provider": payload.get("owner_org_id", ""),
                "region_code": payload.get("region_code"),
                "source_ref": schema_ref,
                "legacy_object_ref": catalog_code,
                "source": "reverse",
                "schema_ref": schema_ref,
                "draft_field_suggestions": payload.get("draft_field_suggestions") or [],
                "created_by_audit": audit_id,
            },
            tenant_id=_DEFAULT_TENANT_ID,
        )
        brain._append_audit_feed("catalog.entry.reverse_draft.create", catalog_code, "ok", actor)
        return {"catalog_code": catalog_code, "lifecycle_status": "draft", "schema_ref": schema_ref, "audit_id": audit_id}

    return brain._mutate("catalog.entry.reverse_draft.create", role, confirmed, payload, mutation)

def _confirm_catalog_entry_reverse_draft(brain, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    catalog_code = str(payload["catalog_code"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        store = brain._state_store.database_store
        repo = store.catalog_repo if store is not None else CatalogRepository()
        existing = repo.get_entry(catalog_code, tenant_id=_DEFAULT_TENANT_ID)
        if existing is None:
            raise NotFoundError(catalog_code)
        summary = copy.deepcopy(existing.summary_json or {})
        if summary.get("source") != "reverse":
            raise InvalidStateError(f"catalog_entry {catalog_code} is not a reverse draft (source={summary.get('source')!r})")
        if existing.lifecycle_status != "draft":
            raise InvalidStateError(f"catalog_entry {catalog_code} is not in draft (current={existing.lifecycle_status})")
        summary["status"] = "pending_review"
        summary["field_decisions"] = payload.get("field_decisions") or []
        summary["confirmation_comment"] = payload.get("comment")
        summary["confirmed_by_audit"] = audit_id
        repo.upsert_from_resource(summary, tenant_id=_DEFAULT_TENANT_ID)
        brain._append_audit_feed("catalog.entry.reverse_draft.confirm", catalog_code, "ok", actor)
        return {"catalog_code": catalog_code, "lifecycle_status": "pending_review", "audit_id": audit_id}

    return brain._mutate("catalog.entry.reverse_draft.confirm", role, confirmed, payload, mutation)

def _reject_catalog_entry_reverse_draft(brain, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    catalog_code = str(payload["catalog_code"])
    reason = str(payload["reject_reason"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        store = brain._state_store.database_store
        repo = store.catalog_repo if store is not None else CatalogRepository()
        existing = repo.get_entry(catalog_code, tenant_id=_DEFAULT_TENANT_ID)
        if existing is None:
            raise NotFoundError(catalog_code)
        summary = copy.deepcopy(existing.summary_json or {})
        if summary.get("source") != "reverse":
            raise InvalidStateError(f"catalog_entry {catalog_code} is not a reverse draft (source={summary.get('source')!r})")
        summary["status"] = "rejected"
        summary["rejected_reason"] = reason
        summary["rejected_by_audit"] = audit_id
        repo.upsert_from_resource(summary, tenant_id=_DEFAULT_TENANT_ID)
        brain._append_audit_feed("catalog.entry.reverse_draft.reject", catalog_code, "ok", actor)
        return {"catalog_code": catalog_code, "lifecycle_status": "rejected", "reason": reason, "audit_id": audit_id}

    return brain._mutate("catalog.entry.reverse_draft.reject", role, confirmed, payload, mutation)

def _review_catalog_entry(brain, catalog_code: str, decision: str, role: str, confirmed: bool) -> dict[str, Any]:
    if decision == "approve":
        return brain.transition_catalog_entry(catalog_code, "approved_pending_publish", "catalog.entry.review", role, confirmed)
    if decision == "return_for_fix":
        return brain.transition_catalog_entry(catalog_code, "draft", "catalog.entry.review", role, confirmed)
    if decision == "reject":
        return brain.transition_catalog_entry(catalog_code, "rejected", "catalog.entry.review", role, confirmed)
    raise BrainServiceError(f"unsupported catalog entry review decision: {decision}")

def _submit_catalog_entry_review(brain, catalog_code: str, role: str, confirmed: bool) -> dict[str, Any]:
    return brain.transition_catalog_entry(catalog_code, "pending_review", "catalog.entry.submit_review", role, confirmed)

def _update_catalog_entry(brain, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    catalog_code = str(payload["catalog_code"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        store = brain._state_store.database_store
        repo = store.catalog_repo if store is not None else CatalogRepository()
        existing = repo.get_entry(catalog_code, tenant_id=_DEFAULT_TENANT_ID)
        if existing is None:
            raise NotFoundError(catalog_code)
        repo.upsert_from_resource(
            {
                **copy.deepcopy(existing.summary_json),
                **brain._safe_json(payload.get("summary_json") or {}),
                "id": catalog_code,
                "name": str(payload.get("title", existing.title)),
                "status": existing.lifecycle_status,
                "provider": payload.get("owner_org_id", existing.owner_org_id or ""),
                "region_code": payload.get("region_code", existing.region_code),
                "source_ref": payload.get("source_ref") or existing.summary_json.get("source_ref"),
                "legacy_object_ref": payload.get("legacy_object_ref") or catalog_code,
            },
            tenant_id=_DEFAULT_TENANT_ID,
        )
        for item in payload.get("items") or []:
            repo.upsert_item({**item, "catalog_code": catalog_code}, tenant_id=_DEFAULT_TENANT_ID)
        brain._append_audit_feed("catalog.entry.update", catalog_code, "ok", actor)
        return {"catalog_code": catalog_code, "lifecycle_status": existing.lifecycle_status, "audit_id": audit_id}

    return brain._mutate("catalog.entry.update", role, confirmed, payload, mutation)


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_catalog_entry_create(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _create_catalog_entry_draft(brain, payload)

def handler_catalog_entry_create_draft(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _create_catalog_entry_draft(brain, payload)

def handler_catalog_entry_publish(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _transition_catalog_entry(brain, str(payload["catalog_code"]), "active", "catalog.entry.publish", str(payload.get("role", brain._ui_state["role"])), bool(payload.get("confirmed")))

def handler_catalog_entry_withdraw(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _transition_catalog_entry(brain, str(payload["catalog_code"]), "retired", "catalog.entry.withdraw", str(payload.get("role", brain._ui_state["role"])), bool(payload.get("confirmed")))

def handler_catalog_entry_query(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _query_catalog_entries(brain, query=payload.get("query"), catalog_code=payload.get("catalog_code"), source=payload.get("source"), lifecycle_status=payload.get("lifecycle_status"))

def handler_catalog_entry_reverse_draft_suggest(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _suggest_catalog_entry_reverse_draft(brain, payload)

def handler_catalog_entry_reverse_draft_create(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _create_catalog_entry_reverse_draft(brain, payload)

def handler_catalog_entry_reverse_draft_confirm(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _confirm_catalog_entry_reverse_draft(brain, payload)

def handler_catalog_entry_reverse_draft_reject(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _reject_catalog_entry_reverse_draft(brain, payload)

def handler_catalog_entry_review(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _review_catalog_entry(brain, str(payload["catalog_code"]), str(payload["decision"]), str(payload.get("role", brain._ui_state["role"])), bool(payload.get("confirmed")))

def handler_catalog_entry_submit_review(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _submit_catalog_entry_review(brain, str(payload["catalog_code"]), str(payload.get("role", brain._ui_state["role"])), bool(payload.get("confirmed")))

def handler_catalog_entry_update(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _update_catalog_entry(brain, payload)

