from __future__ import annotations

from typing import Any

from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

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
    "approval.case.decide.execute": {"r2"},
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
    "catalog.group.query.execute": {"r1", "r2", "r6", "r7", "r8"},
    "catalog.share_zone.query.execute": {"r1", "r2", "r6", "r7", "r8"},
    "catalog.model.query.execute": {"r1", "r2", "r6", "r7", "r8"},
    "catalog.model.field.query.execute": {"r1", "r2", "r6", "r7", "r8"},
    "catalog.entry.query.execute": {"r1", "r2", "r6", "r7", "r8"},
    "catalog.browse.execute": {"r1", "r2", "r6", "r7", "r8"},
    "catalog.entry.create.execute": {"r6", "r7"},
    "catalog.entry.update.execute": {"r6", "r7"},
    "catalog.entry.create_draft.execute": {"r6", "r7"},
    "catalog.entry.submit_review.execute": {"r6", "r7"},
    "catalog.entry.review.execute": {"r7"},
    "catalog.entry.publish.execute": {"r6", "r7"},
    "catalog.entry.withdraw.execute": {"r6", "r7"},
    "catalog.resource.bind.execute": {"r6", "r7"},
    "resource.asset.query.execute": {"r1", "r2", "r6", "r7", "r8"},
    "resource.asset.submit_review.execute": {"r6", "r7"},
    "resource.asset.review.execute": {"r7"},
    "resource.asset.publish.execute": {"r6", "r7"},
    "application.resource.submit.execute": {"r1"},
    "application.resource.review.execute": {"r2"},
    "delivery.access.grant.execute": {"r6"},
    "metadata.schema.query.execute": {"r2", "r5", "r6", "r7", "r8"},
    "metadata.catalog_item.query.execute": {"r2", "r5", "r6", "r7", "r8"},
    "metadata.lineage.query.execute": {"r2", "r5", "r6", "r7", "r8"},
    "metadata.gather.evidence.query.execute": {"r2", "r5", "r6", "r7", "r8"},
    "ops.catalog.statistics.query.execute": {"r2", "r5", "r6", "r7", "r8"},
    "ops.catalog.quality.query.execute": {"r2", "r5", "r6", "r7", "r8"},
    "catalog.manage_entry.execute": {"r6", "r7"},
    "catalog.model.upsert.execute": {"r6", "r7"},
    "catalog.schema.mapping.upsert.execute": {"r6", "r7"},
    "metadata.schema.snapshot.upsert.execute": {"r6", "r7"},
    "metadata.gather.evidence.upsert.execute": {"r6", "r7"},
    "metadata.lineage.upsert.execute": {"r6", "r7", "r8"},
    "ops.catalog.quality.upsert.execute": {"r6", "r7", "r8"},
    "resource.manage_asset.execute": {"r6", "r7"},
    "zone.publish_topic_projection.execute": {"r7"},
    "package.review_decide.execute": {"r7"},
    "capability.package.register.execute": {"r7"},
    "capability.version.submit.execute": {"r7"},
    "capability.version.review.execute": {"r7"},
    "capability.exposure.configure.execute": {"r7"},
    "tenant.capability.enable.execute": {"r7"},
    "tenant.capability.disable.execute": {"r7"},
    "registry.artifact.export.execute": {"r7", "r8"},
    "package.register_version.execute": {"r7"},
    "package.apply_tenant_policy.execute": {"r7"},
    "package.configure_exposure.execute": {"r7"},
    "compliance.investigate_case.execute": {"r8"},
    "compliance.signal.ingest.execute": {"r8"},
    "risk.event.ingest.execute": {"r8"},
    "compliance.rule.configure.execute": {"r8"},
    "compliance.case.open.execute": {"r8"},
    "compliance.case.assign.execute": {"r8"},
    "compliance.case.resolve.execute": {"r8"},
    "compliance.case.close.execute": {"r8"},
    "compliance.case.query.execute": {"r2", "r5", "r6", "r7", "r8"},
    "compliance.metric.query.execute": {"r2", "r5", "r6", "r7", "r8"},
    "dashboard.compliance.query.execute": {"r2", "r5", "r6", "r7", "r8"},
    "standard.asset.sync.execute": {"r7", "r8"},
    "standard.asset.recommend.execute": {"r2", "r5", "r6", "r7", "r8"},
    "security.scan.result.sync.execute": {"r8"},
    "adapter.health.probe.execute": {"r6", "r7", "r8"},
    "objection.case.create.execute": {"r1", "r2", "r5", "r6", "r7", "r8"},
    "objection.case.submit.execute": {"r1", "r2", "r5", "r6", "r7", "r8"},
    "objection.case.accept.execute": {"r2", "r5", "r7", "r8"},
    "objection.case.reject.execute": {"r2", "r5", "r7", "r8"},
    "objection.case.assign.execute": {"r2", "r5", "r7", "r8"},
    "objection.case.reply.execute": {"r5", "r6", "r7", "r8"},
    "objection.case.review.execute": {"r2", "r5", "r7", "r8"},
    "objection.case.evaluate.execute": {"r1", "r2", "r5", "r6", "r7", "r8"},
    "objection.case.escalate.execute": {"r2", "r5", "r7", "r8"},
    "objection.case.close.execute": {"r2", "r5", "r7", "r8"},
    "objection.case.query.execute": {"r1", "r2", "r5", "r6", "r7", "r8"},
    "objection.process.query.execute": {"r1", "r2", "r5", "r6", "r7", "r8"},
    "objection.metric.query.execute": {"r2", "r5", "r7", "r8"},
    "adapter.national.catalog.pull.execute": {"r6", "r7", "r8"},
    "adapter.national.resource.pull.execute": {"r6", "r7", "r8"},
    "adapter.national.catalog.report.execute": {"r6", "r7", "r8"},
    "adapter.national.resource.report.execute": {"r6", "r7", "r8"},
    "adapter.national.application.submit.execute": {"r6", "r7", "r8"},
    "adapter.national.application.receive.execute": {"r6", "r7", "r8"},
    "adapter.national.application.reconcile.execute": {"r6", "r7", "r8"},
    "adapter.national.delivery.receipt.sync.execute": {"r6", "r7", "r8"},
    "adapter.national.objection.sync.execute": {"r6", "r7", "r8"},
    "adapter.national.topic.report.execute": {"r6", "r7", "r8"},
    "adapter.cascade.consume.execute": {"r6", "r7", "r8"},
    "adapter.cascade.replay.execute": {"r6", "r7", "r8"},
    "adapter.cascade.health.query.execute": {"r2", "r5", "r6", "r7", "r8"},
    "adapter.external.mapping.query.execute": {"r2", "r5", "r6", "r7", "r8"},
    "tenant.policy.evaluate.execute": {"r2", "r5", "r6", "r7", "r8"},
    "org.projection.sync.execute": {"r7", "r8"},
    "actor.projection.sync.execute": {"r7", "r8"},
    "legacy.bsp.mapping.import.execute": {"r7", "r8"},
    "legacy.sharezone.mapping.import.execute": {"r7", "r8"},
    "topic.package.create.execute": {"r7"},
    "topic.package.configure.execute": {"r7"},
    "topic.package.submit.execute": {"r7"},
    "topic.package.review.execute": {"r7"},
    "topic.package.publish.execute": {"r7"},
    "topic.package.policy.update.execute": {"r7"},
    "topic.package.subscribe.execute": {"r1", "r2", "r6", "r7", "r8"},
    "topic.package.evidence.attach.execute": {"r2", "r5", "r6", "r7", "r8"},
    "topic.package.query.execute": {"r1", "r2", "r6", "r7", "r8"},
    "topic.package.metric.query.execute": {"r2", "r5", "r6", "r7", "r8"},
    "delivery.receipt.ingest.execute": {"r6", "r7", "r8"},
    "ops.exchange.statistics.query.execute": {"r2", "r5", "r6", "r7", "r8"},
    "ops.exchange.diagnose.execute": {"r2", "r5", "r6", "r7", "r8"},
    "delivery.exchange.plan.execute": {"r6", "r7"},
    "delivery.exchange.start.execute": {"r6", "r7"},
    "delivery.exchange.publish.execute": {"r6", "r7"},
    "delivery.exchange.stop.execute": {"r6", "r7"},
    "application.grant.approve.execute": {"r6"},
    "application.grant.renew.execute": {"r6"},
    "require.intent.submit.execute": {"r1"},
    "require.intent.refine.execute": {"r1"},
    "require.intent.review.execute": {"r2"},
    "require.resource.match.execute": {"r2", "r5", "r6", "r7", "r8"},
    "delivery.subscription.manage.execute": {"r6", "r7"},
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
    return get_runtime_tenant_id()


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
