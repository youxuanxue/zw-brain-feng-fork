from __future__ import annotations

from typing import Any

ACTOR_NAMES = {
    "r1": "周处长",
    "r2": "刘主任",
    "r3": "陈经办",
    "r4": "王网格员",
    "r5": "赵科长",
    "r6": "孙老师",
    "r7": "高主任",
    "r8": "林督查",
}

PERMISSION_ROLES = {
    "workbench.view.execute": {"r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8"},
    "system.snapshot.execute": {"r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8"},
    "system.schema_info.execute": {"r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8"},
    "data.search.execute": {"r1", "r2", "r6", "r7", "r8"},
    "catalog.resource_view.execute": {"r1", "r2", "r6", "r7", "r8"},
    "request.list.execute": {"r1", "r2", "r3", "r4", "r5"},
    "request.view.execute": {"r1", "r2", "r3", "r4", "r5"},
    "approval.view.execute": {"r1", "r2", "r5"},
    "delivery.list.execute": {"r2", "r5", "r6", "r7", "r8"},
    "delivery.view.execute": {"r2", "r5", "r6", "r7", "r8"},
    "provider.view.execute": {"r6", "r7"},
    "governance.dispute_list.execute": {"r2", "r5", "r6", "r7", "r8"},
    "governance.dispute_view.execute": {"r2", "r5", "r6", "r7", "r8"},
    "audit.replay_evidence_chain.execute": {"r2", "r5", "r6", "r7", "r8"},
    "audit.list.execute": {"r2", "r5", "r6", "r7", "r8"},
    "zone.list.execute": {"r1", "r2", "r6", "r7", "r8"},
    "zone.view.execute": {"r1", "r2", "r6", "r7", "r8"},
    "package.list.execute": {"r7"},
    "package.view.execute": {"r7"},
    "dashboard.render_command_center.execute": {"r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8"},
    "request.create.execute": {"r1"},
    "request.submit.execute": {"r1"},
    "approval.review_decide.execute": {"r2"},
    "supplement.submit.execute": {"r3", "r4"},
    "summary.confirm.execute": {"r5"},
    "backflow.confirm.execute": {"r6"},
    "delivery.reconcile_receipt.execute": {"r6"},
    "delivery.trigger_recovery.execute": {"r6"},
    "service.publish_or_suspend.execute": {"r6"},
    "ops.gateway.heartbeat.ingest.execute": {"r6", "r8"},
    "ops.gateway.log.anchor.execute": {"r6", "r8"},
    "ops.service.invocation.query.execute": {"r2", "r5", "r6", "r7", "r8"},
    "ops.service.report.query.execute": {"r2", "r5", "r6", "r7", "r8"},
    "resource.api.register.execute": {"r6", "r7"},
    "resource.api.change.execute": {"r6", "r7"},
    "resource.api.submit_review.execute": {"r6", "r7"},
    "resource.api.review.execute": {"r7"},
    "resource.api.publish.execute": {"r6", "r7"},
    "resource.api.withdraw.execute": {"r6", "r7"},
    "resource.api.revoke.execute": {"r6", "r7"},
    "resource.api.test.execute": {"r6", "r7"},
    "resource.api.policy.update.execute": {"r6", "r7"},
    "catalog.manage_entry.execute": {"r6", "r7"},
    "resource.manage_asset.execute": {"r6", "r7"},
    "zone.publish_topic_projection.execute": {"r7"},
    "package.review_decide.execute": {"r7"},
    "package.register_version.execute": {"r7"},
    "package.apply_tenant_policy.execute": {"r7"},
    "package.configure_exposure.execute": {"r7"},
    "compliance.investigate_case.execute": {"r8"},
    "system.toggle_outage.execute": {"r8"},
}


class DomainAccessDeniedError(PermissionError):
    pass


def resolve_role(payload_role: object, fallback_role: str) -> str:
    role = str(payload_role or fallback_role)
    if role not in ACTOR_NAMES:
        raise DomainAccessDeniedError(f"unknown role: {role}")
    return role


def actor_for_role(role: str) -> str:
    if role not in ACTOR_NAMES:
        raise DomainAccessDeniedError(f"unknown role: {role}")
    return f"user:gov:{role}:{ACTOR_NAMES[role]}"


def tenant_for_role(role: str) -> str:
    if role not in ACTOR_NAMES:
        raise DomainAccessDeniedError(f"unknown role: {role}")
    return "default"


def permissions_for_role(role: str) -> set[str]:
    if role not in ACTOR_NAMES:
        raise DomainAccessDeniedError(f"unknown role: {role}")
    return {permission for permission, roles in PERMISSION_ROLES.items() if role in roles}


def enforce_manifest_policy(skill_id: str, manifest: dict[str, Any], role: str, payload: dict[str, Any]) -> None:
    tenant_scope = manifest.get("tenant_scope")
    if tenant_scope == "tenant":
        requested_tenant = payload["tenant_id"] if "tenant_id" in payload else tenant_for_role(role)
        if requested_tenant != tenant_for_role(role):
            raise DomainAccessDeniedError(f"tenant scope violation for {skill_id}: {requested_tenant}")

    if manifest.get("human_confirmation_required") and not bool(payload.get("confirmed")):
        return

    if not manifest.get("side_effects") and "role" not in payload:
        return

    required_permissions = set(manifest.get("permissions", []))
    missing_permissions = sorted(required_permissions - permissions_for_role(role))
    if missing_permissions:
        raise DomainAccessDeniedError(f"role {role} lacks permissions for {skill_id}: {', '.join(missing_permissions)}")
