"""J2 topic_package handlers — 9 cap migrated from BrainService (F1 turn 4).

Method bodies physically migrated; `self.` → `brain.` substitution applied. Per-cap handler
functions registered in `zw_brain.command.dispatch.DISPATCH_TABLE`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService

from zw_brain.command.brain import InvalidStateError, NotFoundError
from zw_brain.domain.repositories.topic_package import TopicPackageStateError
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEFAULT_TENANT_ID = get_runtime_tenant_id()


# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _configure_topic_package(brain, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    package_code = str(payload["package_code"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        try:
            record = brain._topic_package_repo().configure_package(package_code, payload | {"actor_snapshot_json": {"actor": actor, "role": role}})
        except KeyError as exc:
            raise NotFoundError(package_code) from exc
        brain._append_audit_feed("topic.package.configure", package_code, "ok", actor)
        return brain._topic_package_record_to_dict(record) | {"audit_id": audit_id}

    return brain._mutate("topic.package.configure", role, confirmed, payload, mutation)

def _transition_topic_package(brain, package_code: str, next_status: str, action_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        try:
            record = brain._topic_package_repo().transition_package(
                package_code,
                next_status,
                payload | {"action_type": action_type, "actor_snapshot_json": {"actor": actor, "role": role}},
            )
        except KeyError as exc:
            raise NotFoundError(package_code) from exc
        except TopicPackageStateError as exc:
            raise InvalidStateError(str(exc)) from exc
        brain._append_audit_feed(f"topic.package.{action_type}", package_code, "ok", actor)
        return brain._topic_package_record_to_dict(record) | {"audit_id": audit_id}

    return brain._mutate(f"topic.package.{action_type}", role, confirmed, {"package_code": package_code, "next_status": next_status} | payload, mutation)

def _update_topic_package_policy(brain, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    package_code = str(payload["package_code"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        try:
            records = brain._topic_package_repo().update_policy(package_code, payload | {"actor_snapshot_json": {"actor": actor, "role": role}})
        except KeyError as exc:
            raise NotFoundError(package_code) from exc
        brain._append_audit_feed("topic.package.policy.update", package_code, "ok", actor)
        return {"items": [brain._topic_visibility_record_to_dict(item) for item in records], "total": len(records), "audit_id": audit_id}

    return brain._mutate("topic.package.policy.update", role, confirmed, payload, mutation)

def _subscribe_topic_package(brain, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    package_code = str(payload["package_code"])
    subscription = {
        "visibility_code": str(
            payload.get("visibility_code")
            or f"{payload.get('org_code', '*')}:{payload.get('role_code', '*')}:{package_code}:subscription:use"
        ),
        "org_code": payload.get("org_code"),
        "role_code": payload.get("role_code"),
        "region_code": payload.get("region_code"),
        "surface": "subscription",
        "intent": "use",
        "policy_status": str(payload.get("policy_status", "pending_review")),
        "condition_json": payload.get("condition_json") or payload.get("condition") or {},
    }

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        try:
            records = brain._topic_package_repo().update_policy(
                package_code,
                payload | {"visibility": [subscription], "actor_snapshot_json": {"actor": actor, "role": role}},
            )
        except KeyError as exc:
            raise NotFoundError(package_code) from exc
        brain._append_audit_feed("topic.package.subscribe", package_code, "ok", actor)
        return {
            "package_code": package_code,
            "items": [brain._topic_visibility_record_to_dict(item) for item in records],
            "total": len(records),
            "audit_id": audit_id,
        }

    return brain._mutate("topic.package.subscribe", role, confirmed, payload, mutation)

def _attach_topic_package_evidence(brain, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    package_code = str(payload["package_code"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        try:
            record = brain._topic_package_repo().attach_evidence(package_code, payload | {"actor_snapshot_json": {"actor": actor, "role": role}})
        except KeyError as exc:
            raise NotFoundError(package_code) from exc
        brain._append_audit_feed("topic.package.evidence.attach", package_code, "ok", actor)
        return brain._topic_evidence_record_to_dict(record) | {"audit_id": audit_id}

    return brain._mutate("topic.package.evidence.attach", role, confirmed, payload, mutation)

def _query_topic_packages(brain, *, package_code: Any = None, status: Any = None) -> dict[str, Any]:
    repo = brain._topic_package_repo()
    if package_code:
        record = repo.get_package(str(package_code), tenant_id=_DEFAULT_TENANT_ID)
        if record is None:
            raise NotFoundError(str(package_code))
        items = [brain._topic_package_detail_to_dict(record)]
    else:
        items = [
            brain._topic_package_list_projection(item)
            for item in repo.list_packages(tenant_id=_DEFAULT_TENANT_ID, status=str(status) if status else None)
        ]
    return {"items": items, "total": len(items)}

def _query_topic_package_metrics(brain, *, package_code: Any = None) -> dict[str, Any]:
    repo = brain._topic_package_repo()
    packages = [repo.get_package(str(package_code))] if package_code else repo.list_packages()
    packages = [item for item in packages if item is not None]
    metrics = []
    for package in packages:
        metrics.extend(brain._topic_metric_record_to_dict(item) for item in repo.list_metrics(package.package_code))
    return {
        "items": metrics,
        "summary": {
            "package_count": len(packages),
            "published_count": sum(1 for item in packages if item.status == "published"),
            "metric_count": len(metrics),
        },
    }


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_topic_package_configure(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _configure_topic_package(brain, payload)

def handler_topic_package_submit(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _transition_topic_package(brain, str(payload["package_code"]), "submitted", "submit", payload)

def handler_topic_package_review(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    decision = str(payload["decision"])
    return _transition_topic_package(brain, str(payload["package_code"]), "published" if decision == "approve" else "rejected", "review", payload)

def handler_topic_package_publish(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _transition_topic_package(brain, str(payload["package_code"]), "published", "publish", payload)

def handler_topic_package_policy_update(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _update_topic_package_policy(brain, payload)

def handler_topic_package_subscribe(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _subscribe_topic_package(brain, payload)

def handler_topic_package_evidence_attach(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _attach_topic_package_evidence(brain, payload)

def handler_topic_package_query(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _query_topic_packages(brain, package_code=payload.get("package_code"), status=payload.get("status"))

def handler_topic_package_metric_query(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _query_topic_package_metrics(brain, package_code=payload.get("package_code"))

