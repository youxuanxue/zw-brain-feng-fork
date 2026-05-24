"""J1 objection handlers — 13 cap migrated from BrainService (F1 turn 6, J1 收官)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService


from zw_brain.command.brain import InvalidStateError, NotFoundError
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEFAULT_TENANT_ID = get_runtime_tenant_id()


# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _create_objection_case(brain, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        repo = brain._objection_repo()
        record = repo.create_case(
            payload
            | {
                "actor_snapshot_json": {"actor": actor, "role": role},
                "status": str(payload.get("status", "draft")),
            },
            tenant_id=_DEFAULT_TENANT_ID,
        )
        brain._append_audit_feed("objection.case.create", record.id, "ok", actor)
        return brain._objection_record_to_dict(record) | {"audit_id": audit_id}

    return brain._mutate("objection.case.create", role, confirmed, payload, mutation)

def _transition_objection_case(brain, objection_id: str, next_status: str, action_type: str, node_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        repo = brain._objection_repo()
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
        brain._append_audit_feed(f"objection.case.{action_type}", objection_id, "ok", actor)
        return brain._objection_record_to_dict(record) | {"audit_id": audit_id}

    return brain._mutate(f"objection.case.{action_type}", role, confirmed, {"objection_id": objection_id, "next_status": next_status} | payload, mutation)

def _evaluate_objection_case(brain, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    objection_id = str(payload["objection_id"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        repo = brain._objection_repo()
        try:
            evaluation = repo.evaluate_case(
                objection_id,
                payload | {"evaluator_snapshot_json": {"actor": actor, "role": role} | brain._safe_json(payload.get("evaluator_snapshot_json") or {})},
            )
        except KeyError as exc:
            raise NotFoundError(objection_id) from exc
        except ValueError as exc:
            raise InvalidStateError(str(exc)) from exc
        brain._append_audit_feed("objection.case.evaluate", objection_id, "ok", actor)
        return brain._evaluation_record_to_dict(evaluation) | {"audit_id": audit_id}

    return brain._mutate("objection.case.evaluate", role, confirmed, payload, mutation)

def _query_objection_cases(
    brain,
    *,
    status: Any = None,
    target_type: Any = None,
    target_ref: Any = None,
    target_org_id: Any = None,
    dimension: Any = None,
) -> dict[str, Any]:
    # F4 (E2 J2)：扩 3 个可选 filter 供 J2 提供方收件箱 + 5 维度报表用。
    # target_ref 精确匹配 case.target_id（异议直接挂的实体 ref，如 catalog_code）；
    # target_org_id 精确匹配 case.provider_org_id（异议归属的提供方部门，对 J2 收件箱语义）；
    # dimension 走 objection_state.dimension_of(record, evidences) 推断，对齐 5 维度报表口径。
    # 全部 optional：未传 = 与 PR #90 行为完全一致。
    repo = brain._objection_repo()
    raw_records = list(repo.list_cases(tenant_id=_DEFAULT_TENANT_ID))
    records = [brain._objection_record_to_dict(item) for item in raw_records]
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

def _reply_objection_case(brain, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    objection_id = str(payload["objection_id"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        repo = brain._objection_repo()
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
        brain._append_audit_feed("objection.case.reply", objection_id, "ok", actor)
        return brain._objection_record_to_dict(record) | {"audit_id": audit_id}

    return brain._mutate("objection.case.reply", role, confirmed, payload, mutation)

def _query_objection_metrics(brain) -> dict[str, Any]:
    cases = [brain._objection_record_to_dict(item) for item in brain._objection_repo().list_cases(tenant_id=_DEFAULT_TENANT_ID)]
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

def _query_objection_process(brain, objection_id: str) -> dict[str, Any]:
    if brain._objection_repo().get_case(objection_id, tenant_id=_DEFAULT_TENANT_ID) is None:
        raise NotFoundError(objection_id)
    return {
        "items": [brain._process_record_to_dict(item) for item in brain._objection_repo().list_processes(objection_id)],
        "evidence": [brain._evidence_record_to_dict(item) for item in brain._objection_repo().list_evidence(objection_id)],
    }


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_objection_case_create(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _create_objection_case(brain, payload)

def handler_objection_case_accept(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _transition_objection_case(brain, str(payload["objection_id"]), "accepted", "accept", "受理异议", payload)

def handler_objection_case_assign(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    target_status = str(payload.get("target_status", "provider_investigating"))
    return _transition_objection_case(brain, str(payload["objection_id"]), target_status, "assign", "分发核查", payload)

def handler_objection_case_close(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _transition_objection_case(brain, str(payload["objection_id"]), "closed", "close", "关闭异议", payload)

def handler_objection_case_escalate(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _transition_objection_case(brain, str(payload["objection_id"]), "escalated", "escalate", "升级督办", {"action_result": "escalated"} | payload)

def handler_objection_case_reject(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _transition_objection_case(brain, str(payload["objection_id"]), "rejected", "reject", "驳回异议", payload)

def handler_objection_case_review(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    decision = str(payload["decision"])
    next_status = "resolved" if decision == "resolve" else "provider_investigating"
    return _transition_objection_case(brain, str(payload["objection_id"]), next_status, "review", "复核异议", payload)

def handler_objection_case_submit(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _transition_objection_case(brain, str(payload["objection_id"]), "submitted", "submit", "提交异议", payload)

def handler_objection_case_evaluate(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _evaluate_objection_case(brain, payload)

def handler_objection_case_query(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _query_objection_cases(
        brain,
        status=payload.get("status"),
        target_type=payload.get("target_type"),
        target_ref=payload.get("target_ref"),
        target_org_id=payload.get("target_org_id"),
        dimension=payload.get("dimension"),
    )

def handler_objection_case_reply(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _reply_objection_case(brain, payload)

def handler_objection_metric_query(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _query_objection_metrics(brain)

def handler_objection_process_query(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _query_objection_process(brain, str(payload["objection_id"]))

