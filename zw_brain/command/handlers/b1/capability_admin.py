"""B1 capability_admin handlers — 12 cap migrated from BrainService (F1 turn 5).

Method bodies physically migrated (`self.` → `brain.`); per-cap handler functions
registered in `zw_brain.command.dispatch.DISPATCH_TABLE`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

import copy

from zw_brain.command.brain import BrainServiceError, InvalidStateError
from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEFAULT_TENANT_ID = get_runtime_tenant_id()


# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _register_capability_package(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    package_id = str(payload.get("package_id") or payload.get("id") or f"PKG-{payload['slug']}")
    slug = str(payload["slug"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        packages = deps.brain_legacy._snapshot.setdefault("capability_packages", [])
        item = next((entry for entry in packages if entry.get("id") == package_id or entry.get("slug") == slug), None)
        package_payload = {
            "id": package_id,
            "slug": slug,
            "source": str(payload.get("source", payload.get("source_org", "zw-brain registry"))),
            "status": str(payload.get("status", "pending")),
            "exposure": list(payload.get("exposure") or payload.get("compatibility") or ["api"]),
            "auditClass": str(payload.get("auditClass", payload.get("audit_class", "read-normal"))),
            "requiresHuman": bool(payload.get("requiresHuman", payload.get("requires_human", False))),
            "desc": str(payload.get("desc", payload.get("description", slug))),
            "aiReview": {
                "summary": "能力包已进入统一 registry 候审，正式写权仍由平台 canonical skill 承接。",
                "missing": [],
                "safe": ["统一契约", "不直接改写主事实"],
                "draft": "登记结论：已收件，等待版本审核。",
            },
            "contract": brain._safe_json(payload.get("contract") or {}),
            "tenantPolicy": brain._safe_json(payload.get("tenantPolicy") or {"scope": "tenant-bound", "writeCanonicalState": False, "allowedWritebacks": []}),
            "failureWriteback": brain._safe_json(payload.get("failureWriteback") or {"target": "audit_event", "mode": "failure_summary"}),
            "runtimeBinding": brain._safe_json(payload.get("runtimeBinding") or {"protocol": "brain_service", "sideEffects": ["audit_only"]}),
        }
        if item is None:
            packages.append(package_payload)
        else:
            item.update(package_payload)
        store = deps.state_store.database_store
        if store is not None:
            deps.repos.capability_package.upsert_from_package(package_payload)
        deps.append_audit_feed("capability.package.register", package_id, "ok", actor)
        return {"package_id": package_id, "slug": slug, "status": package_payload["status"], "audit_id": audit_id}

    return deps.write(ctx, payload, mutation)

def _register_package_version(brain, deps, ctx, package_id: str, role: str, confirmed: bool, skill_id: str = "package.register_version") -> dict[str, Any]:
    item = deps.view.packages.find_by_id(package_id)
    if item["status"] != "approved":
        raise InvalidStateError("package must be approved before version registration")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        item["registeredVersion"] = "v1.0.0"
        item["versionStatus"] = "registered"
        item["compatibility"] = item.get("compatibility") or item.get("exposure", [])
        item["tenantScope"] = item.get("tenantScope") or "default"
        item["authPolicy"] = item.get("authPolicy") or "tenant-admin"
        item["rollbackTarget"] = item.get("rollbackTarget") or "v0.9.0"
        item["runtimeBinding"] = item.get("runtimeBinding") or "builtin registry projection"
        item["aiReview"]["summary"] = "版本登记已完成，当前可继续执行租户策略生效，但仍不改变平台对责任写权的控制。"
        item["aiReview"]["draft"] = "登记结论：版本 v1.0.0 已进入 registry，可继续配置租户策略与暴露范围。"
        deps.append_audit_feed(skill_id, package_id, "ok", actor)
        return {"package_id": package_id, "registered_version": item["registeredVersion"]}

    return deps.write(ctx, {"package_id": package_id}, mutation)

def _review_package(brain, deps, ctx, package_id: str, decision: str, role: str, confirmed: bool, skill_id: str = "package.review_decide") -> dict[str, Any]:
    item = deps.view.packages.find_by_id(package_id)

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        if decision == "approve":
            item["status"] = "approved"
            item["versionStatus"] = item.get("versionStatus") or "pending-registration"
            item["tenantScope"] = item.get("tenantScope") or "default"
            item["authPolicy"] = item.get("authPolicy") or "tenant-admin"
            item["compatibility"] = item.get("compatibility") or item.get("exposure", [])
            item["rollbackTarget"] = item.get("rollbackTarget") or "v0.9.0"
            item["runtimeBinding"] = item.get("runtimeBinding") or "builtin registry projection"
            item["aiReview"]["summary"] = "该能力包已通过审核，并限制在只读辅助暴露面内生效。"
            item["aiReview"]["draft"] = "审核结论：批准上线，继续保持只读辅助能力边界，不得声明主状态写权。"
            deps.append_audit_feed("package.approve", package_id, "ok", actor)
        elif decision == "return_for_fix":
            item["status"] = "pending-fix"
            item["aiReview"]["summary"] = "该能力包需要先补齐租户范围或 side effects 声明，当前不进入上线。"
            deps.append_audit_feed("package.return-for-fix", package_id, "warning", actor)
        elif decision == "reject":
            item["status"] = "rejected"
            item["aiReview"]["summary"] = "该能力包因越界写权或暴露面设计不合规被驳回。"
            item["aiReview"]["draft"] = "审核结论：驳回。请回到单一契约并撤销越界写权声明后再重新提交。"
            deps.append_audit_feed("package.reject", package_id, "warning", actor)
        else:
            raise BrainServiceError(f"unsupported package decision: {decision}")
        return {"package_id": package_id, "status": item["status"]}

    return deps.write(ctx, {"package_id": package_id, "decision": decision}, mutation)

def _configure_package_exposure(brain, deps, ctx, package_id: str, mode: str, role: str, confirmed: bool, skill_id: str = "package.configure_exposure") -> dict[str, Any]:
    item = deps.view.packages.find_by_id(package_id)
    if item.get("versionStatus") != "registered":
        raise InvalidStateError("package version must be registered before exposure configuration")
    if mode not in {"tighten", "expand"}:
        raise BrainServiceError(f"unsupported exposure mode: {mode}")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        current = list(item.get("exposure", []))
        if mode == "tighten":
            next_exposure = [surface for surface in current if surface != "mcp"] or current
        else:
            next_exposure = list(dict.fromkeys(current + ["a2a"]))
        item["exposure"] = next_exposure
        item["compatibility"] = next_exposure
        item["aiReview"]["summary"] = f"暴露矩阵已按 {mode} 策略更新，当前仍受统一 capability 契约与审计边界约束。"
        item["aiReview"]["draft"] = f"暴露配置结论：已将 capability surfaces 调整为 {' / '.join(next_exposure)}。"
        deps.append_audit_feed(skill_id, package_id, "ok", actor)
        return {"package_id": package_id, "exposure": next_exposure}

    return deps.write(ctx, {"package_id": package_id, "mode": mode}, mutation)

def _apply_package_tenant_policy(brain, deps, ctx, package_id: str, role: str, confirmed: bool, skill_id: str = "package.apply_tenant_policy", tenant_id: str = _DEFAULT_TENANT_ID) -> dict[str, Any]:
    item = deps.view.packages.find_by_id(package_id)
    if item.get("versionStatus") != "registered":
        raise InvalidStateError("package version must be registered before tenant policy activation")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        item["tenantPolicy"] = {
            "tenantId": tenant_id,
            "policyStatus": "enabled",
            "role_codes": [role],
            "policy": {
                "enabled": True,
                "exposedSurfaces": ["api"],
                "requiresHuman": item.get("requiresHuman", False),
                "auditClass": item.get("auditClass"),
                "tenantPolicy": {"role_codes": [role]},
            },
        }
        item["status"] = "approved"
        store = deps.state_store.database_store
        if store is not None:
            policy_record = deps.repos.capability_package.upsert_tenant_policy(item | {"tenantPolicy": {"role_codes": [role]}}, tenant_id=tenant_id, exposed_surfaces=["api"])
            item["tenantPolicy"] = {
                "tenantId": policy_record.tenant_id,
                "policyStatus": policy_record.policy_status,
                "policy": copy.deepcopy(policy_record.policy_json),
            }
        item["aiReview"]["summary"] = "租户策略已生效，能力包进入可控暴露状态；正式责任写动作仍然回到平台内建能力。"
        item["aiReview"]["draft"] = f"策略结论：{tenant_id} 租户已启用该能力包，暴露面与审计级别沿用已审核结果。"
        deps.append_audit_feed(skill_id, package_id, "ok", actor)
        return {"package_id": package_id, "tenant_policy_status": item["tenantPolicy"]["policyStatus"], "tenant_id": tenant_id}

    return deps.write(ctx, {"package_id": package_id, "tenant_id": tenant_id}, mutation)

def _list_packages(brain, deps, ctx) -> list[dict[str, Any]]:
    items = deps.view.packages.list_all()  # Action C — read facade (already deepcopies)
    store = deps.state_store.database_store
    if store is None:
        return items
    records = {record.package_slug: record for record in deps.repos.capability_package.list_packages()}
    policies = {item.package_slug: item for item in deps.repos.capability_package.list_policies()}
    for item in items:
        record = records.get(item["slug"])
        if record is not None:
            item["status"] = record.review_status
            item["repository"] = {
                "packageSlug": record.package_slug,
                "sourceOrg": record.source_org,
            }
        policy = policies.get(item["slug"])
        if policy is not None:
            item["tenantPolicy"] = {
                **copy.deepcopy(item.get("tenantPolicy", {})),
                "tenantId": policy.tenant_id,
                "policyStatus": policy.policy_status,
                "policy": copy.deepcopy(policy.policy_json),
            }
    return items

def _get_package(brain, deps, ctx, package_id: str) -> dict[str, Any]:
    package = copy.deepcopy(deps.view.packages.find_by_id(package_id))
    store = deps.state_store.database_store
    if store is None:
        return package
    for record in deps.repos.capability_package.list_packages():
        if record.manifest_json.get("id") == package_id or record.package_slug == package.get("slug"):
            package["status"] = record.review_status
            package["repository"] = {
                "packageSlug": record.package_slug,
                "sourceOrg": record.source_org,
            }
            break
    policies = deps.repos.capability_package.list_policies()
    policy = next((item for item in policies if item.package_slug == package.get("slug")), None)
    if policy is not None:
        package["tenantPolicy"] = {
            "tenantId": policy.tenant_id,
            "policyStatus": policy.policy_status,
            "policy": copy.deepcopy(policy.policy_json),
        }
        package["tenantScope"] = policy.tenant_id
    package.setdefault("compatibility", package.get("exposure", []))
    package.setdefault("tenantScope", _DEFAULT_TENANT_ID)
    package.setdefault("authPolicy", "tenant-admin")
    package.setdefault("versionStatus", "pending-registration" if package.get("status") == "approved" else "draft")
    package.setdefault("registeredVersion", "—")
    package.setdefault("rollbackTarget", "v0.9.0")
    package.setdefault("runtimeBinding", "builtin registry projection")
    return package

def _disable_tenant_capability(brain, deps, ctx, package_id: str, role: str, confirmed: bool, tenant_id: str = _DEFAULT_TENANT_ID) -> dict[str, Any]:
    item = deps.view.packages.find_by_id(package_id)

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        item["tenantPolicy"] = {
            "tenantId": tenant_id,
            "policyStatus": "disabled",
            "policy": {
                "enabled": False,
                "exposedSurfaces": [],
                "requiresHuman": item.get("requiresHuman", False),
                "auditClass": item.get("auditClass"),
            },
        }
        store = deps.state_store.database_store
        if store is not None:
            policy_record = deps.repos.capability_package.set_tenant_policy_status(
                item,
                tenant_id=tenant_id,
                policy_status="disabled",
                enabled=False,
                exposed_surfaces=[],
            )
            item["tenantPolicy"] = {
                "tenantId": policy_record.tenant_id,
                "policyStatus": policy_record.policy_status,
                "policy": copy.deepcopy(policy_record.policy_json),
            }
        item["aiReview"]["summary"] = "租户策略已禁用，该能力包不再向当前租户暴露。"
        deps.append_audit_feed("tenant.capability.disable", package_id, "ok", actor)
        return {"package_id": package_id, "tenant_policy_status": item["tenantPolicy"]["policyStatus"], "tenant_id": tenant_id, "audit_id": audit_id}

    return deps.write(ctx, {"package_id": package_id, "tenant_id": tenant_id}, mutation)


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_capability_package_register(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _register_capability_package(brain, deps, ctx, payload)

def handler_capability_version_submit(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _register_package_version(brain, deps, ctx, str(payload["package_id"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")), "capability.version.submit")

def handler_package_register_version(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _register_package_version(brain, deps, ctx, str(payload["package_id"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))

def handler_capability_version_review(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _review_package(brain, deps, ctx, str(payload["package_id"]), str(payload["decision"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")), "capability.version.review")

def handler_package_review_decide(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _review_package(brain, deps, ctx, str(payload["package_id"]), str(payload["decision"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))

def handler_capability_exposure_configure(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _configure_package_exposure(brain, deps, ctx, str(payload["package_id"]), str(payload["mode"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")), "capability.exposure.configure")

def handler_package_configure_exposure(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _configure_package_exposure(brain, deps, ctx, str(payload["package_id"]), str(payload["mode"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))

def handler_package_apply_tenant_policy(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _apply_package_tenant_policy(brain, deps, ctx, str(payload["package_id"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")), tenant_id=str(payload.get("tenant_id", _DEFAULT_TENANT_ID)))

def handler_tenant_capability_enable(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _apply_package_tenant_policy(brain, deps, ctx, str(payload["package_id"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")), "tenant.capability.enable", str(payload.get("tenant_id", _DEFAULT_TENANT_ID)))

def handler_package_list(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return {"items": _list_packages(brain, deps, ctx)}

def handler_package_view(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _get_package(brain, deps, ctx, str(payload["package_id"]))

def handler_tenant_capability_disable(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _disable_tenant_capability(brain, deps, ctx, str(payload["package_id"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")), str(payload.get("tenant_id", _DEFAULT_TENANT_ID)))

