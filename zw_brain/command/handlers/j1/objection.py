"""J1 objection handlers — 13 cap migrated from BrainService (F1 turn 6, J1 收官)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


from sqlalchemy import select

from zw_brain.command.brain import InvalidStateError, NotFoundError
from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.command.serializers import objection as objection_ser
from zw_brain.domain.models import (
    CatalogEntryRecord,
    DeliveryTaskRecord,
    LegacyObjectMappingRecord,
    ResourceAssetRecord,
)
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEFAULT_TENANT_ID = get_runtime_tenant_id()

# Target types that must reference an existing entity. authorization/alert are
# auto-issued by upstream events and not enumerable through a clean lookup;
# they pass validation but caller-supplied ids are still trusted.
_VALIDATED_TARGET_TYPES = {"catalog", "resource", "delivery"}
_KNOWN_TARGET_TYPES = _VALIDATED_TARGET_TYPES | {"authorization", "alert", "content", "use"}


def _target_exists(target_type: str, target_id: str, tenant_id: str) -> bool:
    """True if target_id matches an existing entity for the given type.

    Accepts canonical PK (uuid), canonical business code (catalog_code/
    resource_code/delivery_code), or legacy_object_ref (旧平台主键 — kept
    by M0 import on objection.target_id).
    """
    if target_type not in _VALIDATED_TARGET_TYPES:
        return True  # authorization/alert/content/use — caller-supplied id, no enumerable lookup
    if not target_id:
        return False  # validated type with blank id — reject
    SessionLocal = create_session_factory()
    with SessionLocal() as session:
        if target_type == "catalog":
            hit = session.execute(
                select(CatalogEntryRecord.id).where(
                    CatalogEntryRecord.tenant_id == tenant_id,
                    (CatalogEntryRecord.id == target_id) | (CatalogEntryRecord.catalog_code == target_id),
                ).limit(1)
            ).first()
            if hit:
                return True
            legacy_types = ("data_catalog",)
            canonical_type = "catalog_entry"
        elif target_type == "resource":
            hit = session.execute(
                select(ResourceAssetRecord.id).where(
                    ResourceAssetRecord.tenant_id == tenant_id,
                    (ResourceAssetRecord.id == target_id) | (ResourceAssetRecord.resource_code == target_id),
                ).limit(1)
            ).first()
            if hit:
                return True
            legacy_types = ("data_resource",)
            canonical_type = "resource_asset"
        else:  # delivery
            hit = session.execute(
                select(DeliveryTaskRecord.id).where(
                    DeliveryTaskRecord.tenant_id == tenant_id,
                    (DeliveryTaskRecord.id == target_id) | (DeliveryTaskRecord.delivery_code == target_id),
                ).limit(1)
            ).first()
            if hit:
                return True
            legacy_types = ("data_apply",)
            canonical_type = "delivery_task"
        # legacy id fallback — M0 keeps 旧平台 PK on objection.target_id
        legacy_hit = session.execute(
            select(LegacyObjectMappingRecord.id).where(
                LegacyObjectMappingRecord.tenant_id == tenant_id,
                LegacyObjectMappingRecord.legacy_object_type.in_(legacy_types),
                LegacyObjectMappingRecord.legacy_object_ref == target_id,
                LegacyObjectMappingRecord.canonical_type == canonical_type,
            ).limit(1)
        ).first()
        return bool(legacy_hit)


# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _create_objection_case(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))

    target_type = str(payload.get("target_type") or "").strip()
    target_id = str(payload.get("target_id") or "").strip()
    if target_type not in _KNOWN_TARGET_TYPES:
        raise InvalidStateError(
            f"未知对象类型 {target_type!r}；允许 {sorted(_KNOWN_TARGET_TYPES)}"
        )
    if not _target_exists(target_type, target_id, _DEFAULT_TENANT_ID):
        raise InvalidStateError(
            f"对象不存在：{target_type}={target_id!r}（请从下拉选已存在的对象编号）"
        )

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        repo = deps.repos.objection
        record = repo.create_case(
            payload
            | {
                "actor_snapshot_json": {"actor": actor, "role": role},
                "status": str(payload.get("status", "draft")),
            },
            tenant_id=_DEFAULT_TENANT_ID,
        )
        deps.append_audit_feed("objection.case.create", record.id, "ok", actor)
        return objection_ser.case_to_dict(record) | {"audit_id": audit_id}

    return deps.write(ctx, payload, mutation)

def _transition_objection_case(brain, deps, ctx, objection_id: str, next_status: str, action_type: str, node_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        repo = deps.repos.objection
        try:
            record = repo.transition_case(
                objection_id,
                next_status,
                action_type=action_type,
                node_name=node_name,
                action_result=str(payload.get("action_result", "pass")),
                handler_org_id=payload.get("handler_org_id"),
                handler_snapshot_json={"actor": actor, "role": role} | brain._safe_json(payload.get("handler_snapshot_json") or {}),
                opinion=payload.get("opinion") or payload.get("decision_reason") or payload.get("resolved_summary"),
                resolved_summary=payload.get("resolved_summary"),
                evidence=payload.get("evidence") or [],
            )
        except KeyError as exc:
            raise NotFoundError(objection_id) from exc
        except ValueError as exc:
            raise InvalidStateError(str(exc)) from exc
        deps.append_audit_feed(f"objection.case.{action_type}", objection_id, "ok", actor)
        return objection_ser.case_to_dict(record) | {"audit_id": audit_id}

    return deps.write(ctx, {"objection_id": objection_id, "next_status": next_status} | payload, mutation)

def _evaluate_objection_case(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    objection_id = str(payload["objection_id"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        repo = deps.repos.objection
        try:
            evaluation = repo.evaluate_case(
                objection_id,
                payload | {"evaluator_snapshot_json": {"actor": actor, "role": role} | brain._safe_json(payload.get("evaluator_snapshot_json") or {})},
            )
        except KeyError as exc:
            raise NotFoundError(objection_id) from exc
        except ValueError as exc:
            raise InvalidStateError(str(exc)) from exc
        deps.append_audit_feed("objection.case.evaluate", objection_id, "ok", actor)
        return objection_ser.evaluation_to_dict(evaluation) | {"audit_id": audit_id}

    return deps.write(ctx, payload, mutation)

def _query_objection_cases(
    brain,
    deps,
    ctx,
    *,
    status: Any = None,
    target_type: Any = None,
    target_ref: Any = None,
    target_org_id: Any = None,
    dimension: Any = None,
) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    # F4 (E2 J2)：扩 3 个可选 filter 供 J2 提供方收件箱 + 5 维度报表用。
    # target_ref 精确匹配 case.target_id（异议直接挂的实体 ref，如 catalog_code）；
    # target_org_id 精确匹配 case.provider_org_id（异议归属的提供方部门，对 J2 收件箱语义）；
    # dimension 走 objection_state.dimension_of(record, evidences) 推断，对齐 5 维度报表口径。
    # 全部 optional：未传 = 与 PR #90 行为完全一致。
    repo = deps.repos.objection
    raw_records = list(repo.list_cases(tenant_id=_DEFAULT_TENANT_ID))
    records = [objection_ser.case_to_dict(item) for item in raw_records]
    if status:
        records = [item for item in records if item["status"] == str(status)]
    if target_type:
        records = [item for item in records if item["target_type"] == str(target_type)]
    if target_ref is not None:
        wanted = str(target_ref)
        records = [item for item in records if str(item.get("target_id")) == wanted]
    if target_org_id is not None:
        wanted = str(target_org_id)
        records = [
            item for item in records
            if str(item.get("provider_org_id") or "") == wanted
        ]
    if dimension is not None:
        from zw_brain.domain.objection_state import dimension_of  # noqa: PLC0415
        wanted_dim = str(dimension)
        raw_by_id = {item.id: item for item in raw_records}
        kept: list[dict[str, Any]] = []
        for record in records:
            raw = raw_by_id.get(record["id"])
            if raw is None:
                continue
            evidences = list(repo.list_evidence(record["id"]))
            if dimension_of(raw, evidences) == wanted_dim:
                kept.append(record)
        records = kept
    return {"items": records, "total": len(records)}

def _reply_objection_case(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    objection_id = str(payload["objection_id"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        repo = deps.repos.objection
        try:
            record = repo.add_process(
                objection_id,
                node_name=str(payload.get("node_name", "提交核查回复")),
                action_type="reply",
                action_result=str(payload.get("action_result", "submitted")),
                handler_org_id=payload.get("handler_org_id"),
                handler_snapshot_json={"actor": actor, "role": role} | brain._safe_json(payload.get("handler_snapshot_json") or {}),
                opinion=payload.get("opinion"),
                evidence=payload.get("evidence") or [],
            )
        except KeyError as exc:
            raise NotFoundError(objection_id) from exc
        deps.append_audit_feed("objection.case.reply", objection_id, "ok", actor)
        return objection_ser.case_to_dict(record) | {"audit_id": audit_id}

    return deps.write(ctx, payload, mutation)

def _query_objection_metrics(brain, deps, ctx) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    cases = [objection_ser.case_to_dict(item) for item in deps.repos.objection.list_cases(tenant_id=_DEFAULT_TENANT_ID)]
    by_status: dict[str, int] = {}
    for item in cases:
        by_status[item["status"]] = by_status.get(item["status"], 0) + 1
    closed_count = by_status.get("closed", 0)
    resolved_count = by_status.get("resolved", 0) + closed_count
    return {
        "total": len(cases),
        "by_status": by_status,
        "resolved_count": resolved_count,
        "closed_count": closed_count,
        "open_count": len(cases) - closed_count,
    }

def _query_objection_process(brain, deps, ctx, objection_id: str) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    if deps.repos.objection.get_case(objection_id, tenant_id=_DEFAULT_TENANT_ID) is None:
        raise NotFoundError(objection_id)
    return {
        "items": [objection_ser.process_to_dict(item) for item in deps.repos.objection.list_processes(objection_id)],
        "evidence": [objection_ser.evidence_to_dict(item) for item in deps.repos.objection.list_evidence(objection_id)],
    }


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_objection_case_create(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _create_objection_case(brain, deps, ctx, payload)

def handler_objection_case_accept(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _transition_objection_case(brain, deps, ctx, str(payload["objection_id"]), "accepted", "accept", "受理异议", payload)

def handler_objection_case_assign(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    target_status = str(payload.get("target_status", "provider_investigating"))
    return _transition_objection_case(brain, deps, ctx, str(payload["objection_id"]), target_status, "assign", "分发核查", payload)

def handler_objection_case_close(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _transition_objection_case(brain, deps, ctx, str(payload["objection_id"]), "closed", "close", "关闭异议", payload)

def handler_objection_case_escalate(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _transition_objection_case(brain, deps, ctx, str(payload["objection_id"]), "escalated", "escalate", "升级督办", {"action_result": "escalated"} | payload)

def handler_objection_case_reject(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _transition_objection_case(brain, deps, ctx, str(payload["objection_id"]), "rejected", "reject", "驳回异议", payload)

def handler_objection_case_review(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    decision = str(payload["decision"])
    next_status = "resolved" if decision == "resolve" else "provider_investigating"
    return _transition_objection_case(brain, deps, ctx, str(payload["objection_id"]), next_status, "review", "复核异议", payload)

def handler_objection_case_submit(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _transition_objection_case(brain, deps, ctx, str(payload["objection_id"]), "submitted", "submit", "提交异议", payload)

def handler_objection_case_evaluate(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _evaluate_objection_case(brain, deps, ctx, payload)

def handler_objection_case_query(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _query_objection_cases(
        brain,
        deps,
        ctx,
        status=payload.get("status"),
        target_type=payload.get("target_type"),
        target_ref=payload.get("target_ref"),
        target_org_id=payload.get("target_org_id"),
        dimension=payload.get("dimension"),
    )

def handler_objection_case_reply(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _reply_objection_case(brain, deps, ctx, payload)

def handler_objection_metric_query(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _query_objection_metrics(brain, deps, ctx)

def handler_objection_process_query(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _query_objection_process(brain, deps, ctx, str(payload["objection_id"]))

