"""J1 resource_api handlers — 14 cap migrated from BrainService (F1 turn 6, J1 收官)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

import copy

import zw_brain.shared.clock as clock
from zw_brain.command.brain import BrainServiceError, InvalidStateError, NotFoundError
from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.command.serializers import resource_api as resource_api_ser
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID
from zw_brain.shared.sanitization import safe_json

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _register_api_resource(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    resource = deps.services.provider.api_payload(payload, default_status="draft")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        result = deps.services.provider.upsert_api_resource(resource)
        binding = payload.get("channel_binding")
        if isinstance(binding, dict):
            deps.services.provider.upsert_api_binding({**binding, "resource_code": resource["resource_code"]})
        deps.append_audit_feed("resource.api.register", resource["resource_code"], "ok", actor)
        return result | {"audit_id": audit_id}

    return deps.write(ctx, resource, mutation)

def _change_api_resource(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    resource = deps.services.provider.api_payload(payload, default_status="draft")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        existing = deps.view.resources.get_api_resource(resource["resource_code"])
        if existing is None:
            raise NotFoundError(resource["resource_code"])
        result = deps.services.provider.upsert_api_resource({**existing, **resource})
        binding = payload.get("channel_binding")
        if isinstance(binding, dict):
            deps.services.provider.upsert_api_binding({**binding, "resource_code": resource["resource_code"]})
        deps.append_audit_feed("resource.api.change", resource["resource_code"], "ok", actor)
        return result | {"audit_id": audit_id}

    return deps.write(ctx, resource, mutation)

def _submit_api_resource_review(brain, deps, ctx, resource_code: str, role: str, confirmed: bool, skill_id: str = "resource.api.submit_review") -> dict[str, Any]:
    # 挂接校验门（kind-scoped）：库表资源字段映射未就绪 → 允许存草稿、阻断提交复核。
    # 仅对 resource_kind=="table" 生效；api / file 路径不受影响（无 mapping_ready 要求）。
    asset = deps.services.provider.find_api_resource(resource_code)
    if asset is not None and asset.get("resource_kind") == "table":
        summary = asset.get("summary_json") or {}
        if not summary.get("mapping_ready"):
            raise InvalidStateError(
                f"库表资源 {resource_code} 字段登记未就绪，不能提交复核（请先补全字段登记）"
            )
    # 直连 _transition_api_resource（real ctx），不走 brain.transition_api_resource 委托 shim：
    # 该 shim 建 skill_id="" 的 stub ctx，经 pipeline emit_audit → get_manifest("") → KeyError
    # （潜伏 bug，submit_review/review 此前无 end-to-end 测试故未暴露；publish 本就直连 ctx 正确）。
    return _transition_api_resource(brain, deps, ctx, resource_code, "pending_review", skill_id, role, confirmed)

def _review_api_resource(brain, deps, ctx, resource_code: str, decision: str, role: str, confirmed: bool, skill_id: str = "resource.api.review") -> dict[str, Any]:
    # 同 _submit_api_resource_review：直连 _transition_api_resource（real ctx）修空 skill_id 潜伏 bug。
    if decision == "approve":
        return _transition_api_resource(brain, deps, ctx, resource_code, "approved_pending_publish", skill_id, role, confirmed)
    if decision == "return_for_fix":
        return _transition_api_resource(brain, deps, ctx, resource_code, "draft", skill_id, role, confirmed)
    raise BrainServiceError(f"unsupported api resource review decision: {decision}")

def _transition_api_resource(brain, deps, ctx, resource_code: str, status: str, skill_id: str, role: str, confirmed: bool) -> dict[str, Any]:
    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        store = deps.state_store.database_store
        if store is None:
            resource = deps.view.resources.get_api_resource(resource_code)
            if resource is None:
                raise NotFoundError(resource_code)
            resource["lifecycle_status"] = status
            resource["updated_at"] = clock.now_datetime()
            result = deps.services.provider.upsert_api_resource(resource)
        else:
            record = deps.repos.resource_api.transition_asset(resource_code, status)
            if record is None:
                raise NotFoundError(resource_code)
            if status == "active" and record.catalog_code:
                deps.repos.catalog.upsert_from_resource(
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
            deps.repos.approval.upsert_api_resource_lifecycle(
                resource_code,
                status,
                actor=actor,
                skill_id=skill_id,
                audit_id=audit_id,
                decision="return" if status in {"draft", "test_failed"} else None,
            )
            result = resource_api_ser.resource_asset_to_dict(record)
        deps.append_audit_feed(skill_id, resource_code, "ok", actor)
        return result | {"audit_id": audit_id}

    return deps.write(ctx, {"resource_code": resource_code, "status": status}, mutation)

def _test_api_resource(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", ctx.role))
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
        "evidence_json": safe_json(payload.get("evidence_json") or {}),
        "legacy_object_ref": payload.get("legacy_object_ref"),
    }

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        store = deps.state_store.database_store
        if store is None:
            resource = deps.view.resources.get_api_resource(resource_code)
            if resource is None:
                raise NotFoundError(resource_code)
            resource["lifecycle_status"] = next_status
            resource["updated_at"] = clock.now_datetime()
            result = deps.services.provider.upsert_api_resource(resource)
            tests = deps.brain_legacy._snapshot.setdefault("api_resource_tests", [])
            test_record = test_payload | {"test_ref": audit_id, "tested_by": actor, "tested_at": clock.now_datetime()}
            tests.append(test_record)
        else:
            record = deps.repos.resource_api.transition_asset(resource_code, next_status)
            if record is None:
                raise NotFoundError(resource_code)
            projection = deps.repos.resource_api.upsert_test_projection(test_payload | {"test_ref": audit_id, "tested_by": actor})
            deps.repos.approval.upsert_api_resource_lifecycle(
                resource_code,
                next_status,
                actor=actor,
                skill_id="resource.api.test",
                audit_id=audit_id,
                decision="return" if next_status == "test_failed" else None,
            )
            result = resource_api_ser.resource_asset_to_dict(record)
            test_record = resource_api_ser.api_test_projection_to_dict(projection)
        deps.append_audit_feed("resource.api.test", resource_code, "ok", actor)
        return result | {"audit_id": audit_id, "test_projection": test_record}

    return deps.write(ctx, test_payload, mutation)

def _update_api_resource_policy(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    resource_code = str(payload["resource_code"])
    binding_code = str(payload["binding_code"])
    policy_payload = safe_json(payload.get("gateway_policy_json", {}))

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        if deps.view.resources.get_api_resource(resource_code) is None:
            raise NotFoundError(resource_code)
        binding = deps.services.provider.find_api_binding(binding_code)
        if binding is None or binding.get("resource_code") != resource_code:
            raise NotFoundError(binding_code)
        binding["gateway_policy_json"] = policy_payload
        result = deps.services.provider.upsert_api_binding(binding)
        deps.append_audit_feed("resource.api.policy.update", resource_code, "ok", actor)
        return result | {"audit_id": audit_id}

    return deps.write(ctx, {"resource_code": resource_code, "binding_code": binding_code}, mutation)

def _query_resource_assets(brain, deps, ctx, *, resource_code: Any = None) -> dict[str, Any]:
    store = deps.state_store.database_store
    if store is None:
        resources = copy.deepcopy(deps.brain_legacy._snapshot.get("api_resources", []))
        if resource_code:
            resources = [item for item in resources if item.get("resource_code") == resource_code]
    else:
        resources = [resource_api_ser.resource_asset_to_dict(item) for item in deps.repos.resource_api.list_assets(tenant_id=_DEFAULT_TENANT_ID)]
        if resource_code:
            resources = [item for item in resources if item["resource_code"] == str(resource_code)]
        # N+1 消除：批量富化（一次性预取 per-resource 表）替代 per-asset 各 ~9 查询。
        resources = deps.services.provider.enrich_resource_assets(resources, store)
    return {"items": resources, "total": len(resources)}

def _manage_resource_asset(
    brain,
    deps,
    ctx,
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
        store = deps.state_store.database_store
        # Action C — provider snapshot is read-then-mutated below (lines ~255);
        # deps.view.provider.get() would return a deepcopy, breaking the in-place
        # mutation. Use brain_legacy escape hatch until Action D retires the dict.
        provider = deps.brain_legacy._snapshot["provider"]
        snapshot_resource = next((item for item in provider["resources"] if item["id"] == resource_id), None)
        resource_record = deps.repos.resource_api.get_asset(resource_id, tenant_id=_DEFAULT_TENANT_ID) if store is not None else None
        if snapshot_resource is None and resource_record is None:
            raise NotFoundError(resource_id)
        if action == "complete_field_evidence":
            result = deps.services.provider.complete_field_evidence(resource_id, payload, actor, audit_id)
            event_type = "resource.field_evidence.complete"
        elif action == "confirm_field_binding":
            result = deps.services.provider.confirm_field_binding(resource_id, payload, actor, audit_id)
            event_type = "resource.field_binding.confirm"
        elif action == "submit_review":
            result = deps.services.provider.transition_resource(resource_id, "pending_review", actor, audit_id)
            event_type = "resource.submit_review"
        elif action == "request_external_execution":
            result = deps.services.provider.request_external_execution(resource_id, payload, actor, audit_id)
            event_type = "resource.external_execution.request"
        elif action == "publish":
            result = deps.services.provider.transition_resource(resource_id, "active", actor, audit_id)
            event_type = "resource.publish"
        else:
            result = deps.services.provider.transition_resource(resource_id, "suspended", actor, audit_id)
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
            snapshot_resource["updatedAt"] = clock.now_date()
            snapshot_resource.setdefault("evidence", {})[action] = {"audit_id": audit_id, "actor": actor}
        provider["aiGovernance"]["summary"] = "资源治理状态已更新，当前应确认专区是否只消费可见资产。"
        deps.append_audit_feed(event_type, resource_id, "ok", actor)
        return result | {"audit_id": audit_id}

    return deps.write(ctx, deps.services.provider.manage_payload(resource_id, action, payload), mutation)


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_resource_api_register(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _register_api_resource(brain, deps, ctx, payload)

def handler_resource_api_change(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _change_api_resource(brain, deps, ctx, payload)

def handler_resource_api_submit_review(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _submit_api_resource_review(brain, deps, ctx, str(payload["resource_code"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))

def handler_resource_asset_submit_review(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _submit_api_resource_review(brain, deps, ctx, str(payload["resource_code"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")), "resource.asset.submit_review")

def handler_resource_api_review(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _review_api_resource(brain, deps, ctx, str(payload["resource_code"]), str(payload["decision"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))

def handler_resource_asset_review(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _review_api_resource(brain, deps, ctx, str(payload["resource_code"]), str(payload["decision"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")), "resource.asset.review")

def handler_resource_api_publish(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _transition_api_resource(brain, deps, ctx, str(payload["resource_code"]), "active", "resource.api.publish", str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))

def handler_resource_api_revoke(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _transition_api_resource(brain, deps, ctx, str(payload["resource_code"]), "revoked", "resource.api.revoke", str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))

def handler_resource_api_withdraw(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _transition_api_resource(brain, deps, ctx, str(payload["resource_code"]), "retired", "resource.api.withdraw", str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))

def handler_resource_asset_publish(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _transition_api_resource(brain, deps, ctx, str(payload["resource_code"]), "active", "resource.asset.publish", str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))

def handler_resource_api_test(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _test_api_resource(brain, deps, ctx, payload)

def handler_resource_api_policy_update(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _update_api_resource_policy(brain, deps, ctx, payload)

def handler_resource_asset_query(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _query_resource_assets(brain, deps, ctx, resource_code=payload.get("resource_code"))

def handler_resource_manage_asset(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _manage_resource_asset(brain, deps, ctx, str(payload["resource_id"]), str(payload["action"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")), payload)

