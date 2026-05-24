"""J1 resource_api handlers — 14 cap migrated from BrainService (F1 turn 6, J1 收官)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService

import copy

from zw_brain.command.brain import BrainServiceError, InvalidStateError, NotFoundError
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEFAULT_TENANT_ID = get_runtime_tenant_id()


# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _register_api_resource(brain, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    resource = brain._api_payload(payload, default_status="draft")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        result = brain._upsert_api_resource(resource)
        binding = payload.get("channel_binding")
        if isinstance(binding, dict):
            brain._upsert_api_binding({**binding, "resource_code": resource["resource_code"]})
        brain._append_audit_feed("resource.api.register", resource["resource_code"], "ok", actor)
        return result | {"audit_id": audit_id}

    return brain._mutate("resource.api.register", role, confirmed, resource, mutation)

def _change_api_resource(brain, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    resource = brain._api_payload(payload, default_status="draft")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        existing = brain._find_api_resource(resource["resource_code"])
        if existing is None:
            raise NotFoundError(resource["resource_code"])
        result = brain._upsert_api_resource({**existing, **resource})
        binding = payload.get("channel_binding")
        if isinstance(binding, dict):
            brain._upsert_api_binding({**binding, "resource_code": resource["resource_code"]})
        brain._append_audit_feed("resource.api.change", resource["resource_code"], "ok", actor)
        return result | {"audit_id": audit_id}

    return brain._mutate("resource.api.change", role, confirmed, resource, mutation)

def _submit_api_resource_review(brain, resource_code: str, role: str, confirmed: bool, skill_id: str = "resource.api.submit_review") -> dict[str, Any]:
    return brain.transition_api_resource(resource_code, "pending_review", skill_id, role, confirmed)

def _review_api_resource(brain, resource_code: str, decision: str, role: str, confirmed: bool, skill_id: str = "resource.api.review") -> dict[str, Any]:
    if decision == "approve":
        return brain.transition_api_resource(resource_code, "approved_pending_publish", skill_id, role, confirmed)
    if decision == "return_for_fix":
        return brain.transition_api_resource(resource_code, "draft", skill_id, role, confirmed)
    raise BrainServiceError(f"unsupported api resource review decision: {decision}")

def _transition_api_resource(brain, resource_code: str, status: str, skill_id: str, role: str, confirmed: bool) -> dict[str, Any]:
    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        store = brain._state_store.database_store
        if store is None:
            resource = brain._find_api_resource(resource_code)
            if resource is None:
                raise NotFoundError(resource_code)
            resource["lifecycle_status"] = status
            resource["updated_at"] = brain._now_datetime()
            result = brain._upsert_api_resource(resource)
        else:
            record = store.resource_api_repo.transition_asset(resource_code, status)
            if record is None:
                raise NotFoundError(resource_code)
            if status == "active" and record.catalog_code:
                store.catalog_repo.upsert_from_resource(
                    {
                        "id": record.catalog_code,
                        "name": record.title,
                        "status": "active",
                        "provider": record.owner_org_id or "",
                        "resource_code": record.resource_code,
                        "source_ref": record.source_ref,
                        "legacy_object_ref": record.resource_code,
                        "desc": record.summary_json.get("desc") or record.summary_json.get("title") or record.title,
                        "region_code": record.region_code,
                        "fields": record.summary_json.get("fields", []),
                        "explain": record.summary_json.get("explain", []),
                    }
                )
            store.approval_repo.upsert_api_resource_lifecycle(
                resource_code,
                status,
                actor=actor,
                skill_id=skill_id,
                audit_id=audit_id,
                decision="return" if status in {"draft", "test_failed"} else None,
            )
            result = brain._resource_asset_record_to_dict(record)
        brain._append_audit_feed(skill_id, resource_code, "ok", actor)
        return result | {"audit_id": audit_id}

    return brain._mutate(skill_id, role, confirmed, {"resource_code": resource_code, "status": status}, mutation)

def _test_api_resource(brain, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    resource_code = str(payload["resource_code"])
    test_result = str(payload["test_result"])
    if test_result not in {"passed", "failed"}:
        raise BrainServiceError(f"unsupported api test result: {test_result}")
    next_status = "approved" if test_result == "passed" else "test_failed"
    test_payload = {
        "resource_code": resource_code,
        "binding_code": payload.get("binding_code"),
        "test_result": test_result,
        "lifecycle_status": next_status,
        "source_ref": payload.get("source_ref") or f"resource.api.test:{resource_code}",
        "evidence_json": brain._safe_json(payload.get("evidence_json") or {}),
        "legacy_object_ref": payload.get("legacy_object_ref"),
    }

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        store = brain._state_store.database_store
        if store is None:
            resource = brain._find_api_resource(resource_code)
            if resource is None:
                raise NotFoundError(resource_code)
            resource["lifecycle_status"] = next_status
            resource["updated_at"] = brain._now_datetime()
            result = brain._upsert_api_resource(resource)
            tests = brain._snapshot.setdefault("api_resource_tests", [])
            test_record = test_payload | {"test_ref": audit_id, "tested_by": actor, "tested_at": brain._now_datetime()}
            tests.append(test_record)
        else:
            record = store.resource_api_repo.transition_asset(resource_code, next_status)
            if record is None:
                raise NotFoundError(resource_code)
            projection = store.resource_api_repo.upsert_test_projection(test_payload | {"test_ref": audit_id, "tested_by": actor})
            store.approval_repo.upsert_api_resource_lifecycle(
                resource_code,
                next_status,
                actor=actor,
                skill_id="resource.api.test",
                audit_id=audit_id,
                decision="return" if next_status == "test_failed" else None,
            )
            result = brain._resource_asset_record_to_dict(record)
            test_record = brain._api_test_projection_record_to_dict(projection)
        brain._append_audit_feed("resource.api.test", resource_code, "ok", actor)
        return result | {"audit_id": audit_id, "test_projection": test_record}

    return brain._mutate("resource.api.test", role, confirmed, test_payload, mutation)

def _update_api_resource_policy(brain, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    resource_code = str(payload["resource_code"])
    binding_code = str(payload["binding_code"])
    policy_payload = brain._safe_json(payload.get("gateway_policy_json", {}))

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        if brain._find_api_resource(resource_code) is None:
            raise NotFoundError(resource_code)
        binding = brain._find_api_binding(binding_code)
        if binding is None or binding.get("resource_code") != resource_code:
            raise NotFoundError(binding_code)
        binding["gateway_policy_json"] = policy_payload
        result = brain._upsert_api_binding(binding)
        brain._append_audit_feed("resource.api.policy.update", resource_code, "ok", actor)
        return result | {"audit_id": audit_id}

    return brain._mutate("resource.api.policy.update", role, confirmed, {"resource_code": resource_code, "binding_code": binding_code}, mutation)

def _query_resource_assets(brain, *, resource_code: Any = None) -> dict[str, Any]:
    store = brain._state_store.database_store
    if store is None:
        resources = copy.deepcopy(brain._snapshot.get("api_resources", []))
        if resource_code:
            resources = [item for item in resources if item.get("resource_code") == resource_code]
    else:
        resources = [brain._resource_asset_record_to_dict(item) for item in store.resource_api_repo.list_assets(tenant_id=_DEFAULT_TENANT_ID)]
        if resource_code:
            resources = [item for item in resources if item["resource_code"] == str(resource_code)]
        resources = [brain._enrich_provider_resource_asset(item, store) for item in resources]
    return {"items": resources, "total": len(resources)}

def _manage_resource_asset(
    brain,
    resource_id: str,
    action: str,
    role: str,
    confirmed: bool,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = payload or {"resource_id": resource_id, "action": action}
    allowed_actions = {
        "publish",
        "suspend",
        "complete_field_evidence",
        "confirm_field_binding",
        "submit_review",
        "request_external_execution",
    }
    if action not in allowed_actions:
        raise InvalidStateError(f"unsupported resource action: {action}")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        store = brain._state_store.database_store
        provider = brain._snapshot["provider"]
        snapshot_resource = next((item for item in provider["resources"] if item["id"] == resource_id), None)
        resource_record = store.resource_api_repo.get_asset(resource_id, tenant_id=_DEFAULT_TENANT_ID) if store is not None else None
        if snapshot_resource is None and resource_record is None:
            raise NotFoundError(resource_id)
        if action == "complete_field_evidence":
            result = brain._complete_provider_field_evidence(resource_id, payload, actor, audit_id)
            event_type = "resource.field_evidence.complete"
        elif action == "confirm_field_binding":
            result = brain._confirm_provider_field_binding(resource_id, payload, actor, audit_id)
            event_type = "resource.field_binding.confirm"
        elif action == "submit_review":
            result = brain._transition_provider_resource(resource_id, "pending_review", actor, audit_id)
            event_type = "resource.submit_review"
        elif action == "request_external_execution":
            result = brain._request_provider_external_execution(resource_id, payload, actor, audit_id)
            event_type = "resource.external_execution.request"
        elif action == "publish":
            result = brain._transition_provider_resource(resource_id, "active", actor, audit_id)
            event_type = "resource.publish"
        else:
            result = brain._transition_provider_resource(resource_id, "suspended", actor, audit_id)
            event_type = "resource.suspend"
        if snapshot_resource is not None:
            status = {
                "complete_field_evidence": "证据已补齐",
                "confirm_field_binding": "字段绑定已确认",
                "submit_review": "待审核",
                "request_external_execution": snapshot_resource.get("status", "待外部执行"),
                "publish": "可共享",
                "suspend": "暂停共享",
            }[action]
            snapshot_resource["status"] = status
            snapshot_resource["governanceLocked"] = True
            snapshot_resource["updatedAt"] = brain._now_date()
            snapshot_resource.setdefault("evidence", {})[action] = {"audit_id": audit_id, "actor": actor}
        provider["aiGovernance"]["summary"] = "资源治理状态已更新，当前应确认专区是否只消费可见资产。"
        brain._append_audit_feed(event_type, resource_id, "ok", actor)
        return result | {"audit_id": audit_id}

    return brain._mutate("resource.manage_asset", role, confirmed, brain._provider_manage_payload(resource_id, action, payload), mutation)


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_resource_api_register(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _register_api_resource(brain, payload)

def handler_resource_api_change(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _change_api_resource(brain, payload)

def handler_resource_api_submit_review(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _submit_api_resource_review(brain, str(payload["resource_code"]), str(payload.get("role", brain._ui_state["role"])), bool(payload.get("confirmed")))

def handler_resource_asset_submit_review(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _submit_api_resource_review(brain, str(payload["resource_code"]), str(payload.get("role", brain._ui_state["role"])), bool(payload.get("confirmed")), "resource.asset.submit_review")

def handler_resource_api_review(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _review_api_resource(brain, str(payload["resource_code"]), str(payload["decision"]), str(payload.get("role", brain._ui_state["role"])), bool(payload.get("confirmed")))

def handler_resource_asset_review(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _review_api_resource(brain, str(payload["resource_code"]), str(payload["decision"]), str(payload.get("role", brain._ui_state["role"])), bool(payload.get("confirmed")), "resource.asset.review")

def handler_resource_api_publish(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _transition_api_resource(brain, str(payload["resource_code"]), "active", "resource.api.publish", str(payload.get("role", brain._ui_state["role"])), bool(payload.get("confirmed")))

def handler_resource_api_revoke(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _transition_api_resource(brain, str(payload["resource_code"]), "revoked", "resource.api.revoke", str(payload.get("role", brain._ui_state["role"])), bool(payload.get("confirmed")))

def handler_resource_api_withdraw(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _transition_api_resource(brain, str(payload["resource_code"]), "retired", "resource.api.withdraw", str(payload.get("role", brain._ui_state["role"])), bool(payload.get("confirmed")))

def handler_resource_asset_publish(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _transition_api_resource(brain, str(payload["resource_code"]), "active", "resource.asset.publish", str(payload.get("role", brain._ui_state["role"])), bool(payload.get("confirmed")))

def handler_resource_api_test(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _test_api_resource(brain, payload)

def handler_resource_api_policy_update(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _update_api_resource_policy(brain, payload)

def handler_resource_asset_query(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _query_resource_assets(brain, resource_code=payload.get("resource_code"))

def handler_resource_manage_asset(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _manage_resource_asset(brain, str(payload["resource_id"]), str(payload["action"]), str(payload.get("role", brain._ui_state["role"])), bool(payload.get("confirmed")), payload)

