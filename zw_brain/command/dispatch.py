"""brain.py 拆分薄分发器 — 全 185 capability 注册的唯一入口。

`BrainService._dispatch_skill` 直接走 `dispatch.lookup(skill_id)` → handler；
未命中即 raise `UnknownSkillError` (原 match 块已删除，无 fall-through)。

新增 capability 的唯一路径（基线 §11 反 per-tenant fork + R10/R11/R12 三层依赖）：
1. 在对应桶 `handlers/{j1,j2,b1,infra}/<module>.py` 加 handler 函数（签名见下）
2. 在本文件 DISPATCH_TABLE 注册 `"<capability_id>": <module>.<handler_fn>`
3. 在 `handlers/_CATEGORIZATION.md` 补一行 bucket 归属

handler 签名：
    def handler(brain: 'BrainService', skill_id: str, payload: dict[str, Any]) -> Any

共享 method（如 transition_objection_case 服务 7 cap、record_adapter_operation
17 cap 共用）：handler 内派生不同参数后调同一 module-level fn，详见各 handler 模块。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from zw_brain.command.handlers.b1 import (
    approval_flow_schema,
    audit,
    capability_admin,
    exchange_statistics_query,
    form_schema,
    intake,
    investigation,
    ops_catalog,
    ops_exchange,
    ops_gateway,
    ops_service,
    ops_workflow,
    projection,
    projection_status,
    recommendation_rule,
    registry,
    system_ops,
)
from zw_brain.command.handlers.infra import (
    adapter_health_query,
    adapter_mapping_query,
    adapter_passthrough,
    legacy_bsp_mapping,
    legacy_migration_status,
    legacy_sharezone_mapping,
)
from zw_brain.command.handlers.j1 import (
    application_assistants,
    application_grant,
    approval,
    catalog_entry,
    catalog_meta,
    credential,
    data_search,
    delivery,
    delivery_explain,
    direct_access,
    governance_dispute,
    objection,
    provider,
    recommendation_suggest,
    request,
    requirement_intake,
    resource_api,
    search_assistant,
    workbench,
)
from zw_brain.command.handlers.j2 import (
    compliance,
    duplicate_check,
    governance,
    metadata,
    quality,
    service_lifecycle,
    tenant_policy,
    topic_package,
    topic_package_create,
    zone,
)

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService

Handler = Callable[["BrainService", str, dict[str, Any]], Any]

_PASSTHROUGH_CAPS = (
    "adapter.cascade.consume",
    "adapter.cascade.replay",
    "adapter.national.application.receive",
    "adapter.national.application.reconcile",
    "adapter.national.application.submit",
    "adapter.national.catalog.pull",
    "adapter.national.catalog.report",
    "adapter.national.delivery.receipt.sync",
    "adapter.national.objection.sync",
    "adapter.national.resource.pull",
    "adapter.national.resource.report",
    "adapter.national.topic.report",
    "compliance.signal.ingest",
    "risk.event.ingest",
    "standard.asset.recommend",
    "security.scan.result.sync",
)

DISPATCH_TABLE: dict[str, Handler] = {
    # turn 2
    "data.search": data_search.handler,
    # F6: J1 P2 搜索上下文助手（减摩组件，走 shared/inference/client）
    "search.intent.parse": search_assistant.handler_search_intent_parse,
    "topic.package.create": topic_package_create.handler,
    "ops.exchange.statistics.query": exchange_statistics_query.handler,
    # turn 3: infra
    "adapter.health.probe": adapter_passthrough.handler_health_probe,
    "adapter.cascade.health.query": adapter_health_query.handler,
    "adapter.external.mapping.query": adapter_mapping_query.handler,
    "legacy.bsp.mapping.import": legacy_bsp_mapping.handler,
    "legacy.migration.status.query": legacy_migration_status.handler,
    "legacy.sharezone.mapping.import": legacy_sharezone_mapping.handler,
    # F3 (E2 J2): J2 — duplicate_check (1 cap; 发布前重复率检测，read-only 非硬拦)
    "catalog.duplicate.check": duplicate_check.handler_catalog_duplicate_check,
    # turn 4: J2 — compliance (8 cap)
    "compliance.case.open": compliance.handler_compliance_case_open,
    "compliance.case.assign": compliance.handler_compliance_case_assign,
    "compliance.case.close": compliance.handler_compliance_case_close,
    "compliance.case.resolve": compliance.handler_compliance_case_resolve,
    "compliance.case.query": compliance.handler_compliance_case_query,
    "compliance.metric.query": compliance.handler_compliance_metric_query,
    "compliance.rule.configure": compliance.handler_compliance_rule_configure,
    "compliance.investigate_case": compliance.handler_compliance_investigate_case,
    # turn 4: J2 — governance (3 cap)
    "governance.iam_overview": governance.handler_governance_iam_overview,
    "governance.policy_candidate.list": governance.handler_governance_policy_candidate_list,
    "governance.policy_candidate.review": governance.handler_governance_policy_candidate_review,
    # turn 4: J2 — metadata (8 cap)
    "metadata.schema.discover": metadata.handler_metadata_schema_discover,
    "metadata.schema.query": metadata.handler_metadata_schema_query,
    "metadata.catalog_item.query": metadata.handler_metadata_catalog_item_query,
    "metadata.lineage.query": metadata.handler_metadata_lineage_query,
    "metadata.gather.evidence.query": metadata.handler_metadata_gather_evidence_query,
    "metadata.schema.snapshot.upsert": metadata.handler_metadata_schema_snapshot_upsert,
    "metadata.gather.evidence.upsert": metadata.handler_metadata_gather_evidence_upsert,
    "metadata.lineage.upsert": metadata.handler_metadata_lineage_upsert,
    # turn 4: J2 — quality (3 cap)
    "quality.rule.upsert": quality.handler_quality_rule_upsert,
    "quality.task.run": quality.handler_quality_task_run,
    "quality.task.replay": quality.handler_quality_task_replay,
    # turn 4: J2 — topic_package (9 cap; create from turn 2)
    "topic.package.configure": topic_package.handler_topic_package_configure,
    "topic.package.submit": topic_package.handler_topic_package_submit,
    "topic.package.review": topic_package.handler_topic_package_review,
    "topic.package.publish": topic_package.handler_topic_package_publish,
    "topic.package.policy.update": topic_package.handler_topic_package_policy_update,
    "topic.package.subscribe": topic_package.handler_topic_package_subscribe,
    "topic.package.evidence.attach": topic_package.handler_topic_package_evidence_attach,
    "topic.package.query": topic_package.handler_topic_package_query,
    "topic.package.metric.query": topic_package.handler_topic_package_metric_query,
    # turn 4: J2 — zone (3 cap)
    "zone.list": zone.handler_zone_list,
    "zone.view": zone.handler_zone_view,
    "zone.publish_topic_projection": zone.handler_zone_publish_topic_projection,
    # turn 4: J2 — tenant_policy (1 cap)
    "tenant.policy.evaluate": tenant_policy.handler_tenant_policy_evaluate,
    # turn 4: J2 — service_lifecycle (1 cap)
    "service.publish_or_suspend": service_lifecycle.handler_service_publish_or_suspend,
    # turn 5: B1 — projection (2 cap)
    "org.projection.sync": projection.handler_org_projection_sync,
    "actor.projection.sync": projection.handler_actor_projection_sync,
    # F4 turn 1: B1 — projection_status (1 cap, 5 类投影 health aggregator)
    "projection.status.query": projection_status.handler_projection_status_query,
    # turn 5: B1 — audit (8 cap; +2 F2 audit.event.{query,replay}, +4 F3-backend
    # audit.event.{statistics,anomaly,accountability} + assistant.investigation_summary)
    "audit.list": audit.handler_audit_list,
    "audit.replay_evidence_chain": audit.handler_audit_replay_evidence_chain,
    "audit.event.query": audit.handler_audit_event_query,
    "audit.event.replay": audit.handler_audit_event_replay,
    "audit.event.statistics": audit.handler_audit_event_statistics,
    "audit.event.anomaly": audit.handler_audit_event_anomaly,
    "audit.event.accountability": audit.handler_audit_event_accountability,
    "assistant.investigation_summary": investigation.handler_assistant_investigation_summary,
    # turn 5: B1 — ops_catalog (3 cap)
    "ops.catalog.quality.query": ops_catalog.handler_ops_catalog_quality_query,
    "ops.catalog.quality.upsert": ops_catalog.handler_ops_catalog_quality_upsert,
    "ops.catalog.statistics.query": ops_catalog.handler_ops_catalog_statistics_query,
    # turn 5: B1 — ops_exchange (1 cap; ops.exchange.statistics.query in turn 2 b1/exchange_statistics_query.py)
    "ops.exchange.diagnose": ops_exchange.handler_ops_exchange_diagnose,
    # turn 5: B1 — ops_gateway (2 cap)
    "ops.gateway.heartbeat.ingest": ops_gateway.handler_ops_gateway_heartbeat_ingest,
    "ops.gateway.log.anchor": ops_gateway.handler_ops_gateway_log_anchor,
    # turn 5: B1 — ops_service (2 cap)
    "ops.service.invocation.query": ops_service.handler_ops_service_invocation_query,
    "ops.service.report.query": ops_service.handler_ops_service_report_query,
    # turn 5: B1 — ops_workflow (3 cap)
    "ops.ticket.create": ops_workflow.handler_ops_ticket_create,
    "ops.ticket.close": ops_workflow.handler_ops_ticket_close,
    "ops.shift_handover.submit": ops_workflow.handler_ops_shift_handover_submit,
    # turn 5: B1 — capability_admin (12 cap)
    "capability.package.register": capability_admin.handler_capability_package_register,
    "capability.version.submit": capability_admin.handler_capability_version_submit,
    "package.register_version": capability_admin.handler_package_register_version,
    "capability.version.review": capability_admin.handler_capability_version_review,
    "package.review_decide": capability_admin.handler_package_review_decide,
    "capability.exposure.configure": capability_admin.handler_capability_exposure_configure,
    "package.configure_exposure": capability_admin.handler_package_configure_exposure,
    "package.apply_tenant_policy": capability_admin.handler_package_apply_tenant_policy,
    "tenant.capability.enable": capability_admin.handler_tenant_capability_enable,
    "package.list": capability_admin.handler_package_list,
    "package.view": capability_admin.handler_package_view,
    "tenant.capability.disable": capability_admin.handler_tenant_capability_disable,
    # F4 B1.2 intake (3 new cap): rollback / exposure matrix / trust_level
    "package.rollback": intake.handler_package_rollback,
    "package.exposure.matrix.query": intake.handler_package_exposure_matrix_query,
    "package.trust_level.update": intake.handler_package_trust_level_update,
    # turn 5: B1 — registry (1 cap)
    "registry.artifact.export": registry.handler_registry_artifact_export,
    # turn 5: B1 — system_ops (3 cap)
    "system.toggle_outage": system_ops.handler_system_toggle_outage,
    "system.snapshot": system_ops.handler_system_snapshot,
    "system.schema_info": system_ops.handler_system_schema_info,
    # turn 6: J1 — application_grant (4 cap)
    "application.grant.approve": application_grant.handler_application_grant_approve,
    "application.grant.renew": application_grant.handler_application_grant_renew,
    "application.grant.suspend": application_grant.handler_application_grant_suspend,
    "application.grant.revoke": application_grant.handler_application_grant_revoke,
    # turn 6: J1 — approval (4 cap)
    "approval.view": approval.handler_approval_view,
    "application.resource.review": approval.handler_application_resource_review,
    "approval.case.decide": approval.handler_approval_case_decide,
    "approval.review_decide": approval.handler_approval_review_decide,
    # F7: J1 P3 双助手 (减摩组件，走 shared/inference/client + 三层降级)
    "application.draft.suggest": application_assistants.handler_application_draft_suggest,
    "approval.evidence.summarize": application_assistants.handler_approval_evidence_summarize,
    # turn 6: J1 — catalog_entry (12 cap)
    "catalog.entry.create": catalog_entry.handler_catalog_entry_create,
    "catalog.entry.create_draft": catalog_entry.handler_catalog_entry_create_draft,
    "catalog.entry.publish": catalog_entry.handler_catalog_entry_publish,
    "catalog.entry.withdraw": catalog_entry.handler_catalog_entry_withdraw,
    "catalog.entry.query": catalog_entry.handler_catalog_entry_query,
    "catalog.entry.reverse_draft.suggest": catalog_entry.handler_catalog_entry_reverse_draft_suggest,
    "catalog.entry.reverse_draft.create": catalog_entry.handler_catalog_entry_reverse_draft_create,
    "catalog.entry.reverse_draft.confirm": catalog_entry.handler_catalog_entry_reverse_draft_confirm,
    "catalog.entry.reverse_draft.reject": catalog_entry.handler_catalog_entry_reverse_draft_reject,
    "catalog.entry.review": catalog_entry.handler_catalog_entry_review,
    "catalog.entry.submit_review": catalog_entry.handler_catalog_entry_submit_review,
    "catalog.entry.update": catalog_entry.handler_catalog_entry_update,
    # turn 6: J1 — catalog_meta (10 cap)
    "catalog.browse": catalog_meta.handler_catalog_browse,
    "catalog.group.query": catalog_meta.handler_catalog_group_query,
    "catalog.manage_entry": catalog_meta.handler_catalog_manage_entry,
    "catalog.model.query": catalog_meta.handler_catalog_model_query,
    "catalog.model.field.query": catalog_meta.handler_catalog_model_field_query,
    "catalog.model.upsert": catalog_meta.handler_catalog_model_upsert,
    "catalog.resource.bind": catalog_meta.handler_catalog_resource_bind,
    "catalog.resource_view": catalog_meta.handler_catalog_resource_view,
    "catalog.schema.mapping.upsert": catalog_meta.handler_catalog_schema_mapping_upsert,
    "catalog.share_zone.query": catalog_meta.handler_catalog_share_zone_query,
    # turn 6: J1 — credential (3 cap: F5 added sample.render)
    "credential.issue": credential.handler_credential_issue,
    "credential.query": credential.handler_credential_query,
    "credential.sample.render": credential.handler_credential_sample_render,
    # turn 6: J1 — delivery (12 cap)
    "delivery.exchange.plan": delivery.handler_delivery_exchange_plan,
    "delivery.exchange.publish": delivery.handler_delivery_exchange_publish,
    "delivery.exchange.start": delivery.handler_delivery_exchange_start,
    "delivery.exchange.stop": delivery.handler_delivery_exchange_stop,
    "delivery.receipt.ingest": delivery.handler_delivery_receipt_ingest,
    "delivery.reconcile_receipt": delivery.handler_delivery_reconcile_receipt,
    "delivery.replace_or_cancel": delivery.handler_delivery_replace_or_cancel,
    "delivery.subscription.manage": delivery.handler_delivery_subscription_manage,
    "delivery.trigger_recovery": delivery.handler_delivery_trigger_recovery,
    "delivery.view": delivery.handler_delivery_view,
    "delivery.access.grant": delivery.handler_delivery_access_grant,
    "delivery.list": delivery.handler_delivery_list,
    # F8: J1 P4 状态解释助手（减摩组件，走 shared/inference/client + 三层降级）
    "delivery.status.explain": delivery_explain.handler_delivery_status_explain,
    # turn 6: J1 — direct_access (2 cap)
    "direct_access.catalog.query": direct_access.handler_direct_access_catalog_query,
    "direct_access.delivery.list": direct_access.handler_direct_access_delivery_list,
    # turn 6: J1 — governance_dispute (2 cap)
    "governance.dispute_list": governance_dispute.handler_governance_dispute_list,
    "governance.dispute_view": governance_dispute.handler_governance_dispute_view,
    # turn 6: J1 — objection (13 cap)
    "objection.case.create": objection.handler_objection_case_create,
    "objection.case.accept": objection.handler_objection_case_accept,
    "objection.case.assign": objection.handler_objection_case_assign,
    "objection.case.close": objection.handler_objection_case_close,
    "objection.case.escalate": objection.handler_objection_case_escalate,
    "objection.case.reject": objection.handler_objection_case_reject,
    "objection.case.review": objection.handler_objection_case_review,
    "objection.case.submit": objection.handler_objection_case_submit,
    "objection.case.evaluate": objection.handler_objection_case_evaluate,
    "objection.case.query": objection.handler_objection_case_query,
    "objection.case.reply": objection.handler_objection_case_reply,
    "objection.metric.query": objection.handler_objection_metric_query,
    "objection.process.query": objection.handler_objection_process_query,
    # turn 6: J1 — provider (1 cap)
    "provider.view": provider.handler_provider_view,
    # turn 6: J1 — request (5 cap)
    "application.resource.submit": request.handler_application_resource_submit,
    "request.create": request.handler_request_create,
    "request.submit": request.handler_request_submit,
    "request.view": request.handler_request_view,
    "request.list": request.handler_request_list,
    # turn 6: J1 — requirement_intake (9 cap)
    "require.intent.submit": requirement_intake.handler_require_intent_submit,
    "require.intent.refine": requirement_intake.handler_require_intent_refine,
    "require.intent.review": requirement_intake.handler_require_intent_review,
    "require.resource.dispatch": requirement_intake.handler_require_resource_dispatch,
    "require.resource.match": requirement_intake.handler_require_resource_match,
    "require.task.handoff": requirement_intake.handler_require_task_handoff,
    "supplement.submit": requirement_intake.handler_supplement_submit,
    "summary.confirm": requirement_intake.handler_summary_confirm,
    "backflow.confirm": requirement_intake.handler_backflow_confirm,
    # turn 6: J1 — resource_api (14 cap)
    "resource.api.register": resource_api.handler_resource_api_register,
    "resource.api.change": resource_api.handler_resource_api_change,
    "resource.api.submit_review": resource_api.handler_resource_api_submit_review,
    "resource.asset.submit_review": resource_api.handler_resource_asset_submit_review,
    "resource.api.review": resource_api.handler_resource_api_review,
    "resource.asset.review": resource_api.handler_resource_asset_review,
    "resource.api.publish": resource_api.handler_resource_api_publish,
    "resource.api.revoke": resource_api.handler_resource_api_revoke,
    "resource.api.withdraw": resource_api.handler_resource_api_withdraw,
    "resource.asset.publish": resource_api.handler_resource_asset_publish,
    "resource.api.test": resource_api.handler_resource_api_test,
    "resource.api.policy.update": resource_api.handler_resource_api_policy_update,
    "resource.asset.query": resource_api.handler_resource_asset_query,
    "resource.manage_asset": resource_api.handler_resource_manage_asset,
    # turn 6: J1 — workbench (3 cap)
    "workbench.view": workbench.handler_workbench_view,
    "service.rating.submit": workbench.handler_service_rating_submit,
    "subscription.terminate": workbench.handler_subscription_terminate,
    # E3 Wave-2 三引擎 F1 — 审批流模板 commit (1 cap, B1 后台支撑面)
    "approval_flow.schema.commit": approval_flow_schema.handler_approval_flow_schema_commit,
    # E3 Wave-2 三引擎 F3 — NL 草稿 + 三步流程 promote/revert (3 cap, B1)
    "approval_flow.nl_draft": approval_flow_schema.handler_approval_flow_nl_draft,
    "approval_flow.schema.promote_to_preview": approval_flow_schema.handler_approval_flow_schema_promote_to_preview,
    "approval_flow.schema.revert_to_draft": approval_flow_schema.handler_approval_flow_schema_revert_to_draft,
    # E3 Wave-2 三引擎 F4 — 表单模板 commit (1 cap, B1 后台支撑面)
    "form_schema.commit": form_schema.handler_form_schema_commit,
    # E3 Wave-2 三引擎 F5 — 表单 NL 草稿 + 三步流程 promote/revert (3 cap, B1)
    "form_schema.nl_draft": form_schema.handler_form_schema_nl_draft,
    "form_schema.promote_to_preview": form_schema.handler_form_schema_promote_to_preview,
    "form_schema.revert_to_draft": form_schema.handler_form_schema_revert_to_draft,
    # E3 Wave-2 三引擎 F6 — 推荐规则 commit (1 cap, B1) + 相似目录推荐 suggest (1 cap, J1)
    "recommendation.rule.commit": recommendation_rule.handler_recommendation_rule_commit,
    "recommendation.similar_catalog.suggest": recommendation_suggest.handler_recommendation_similar_catalog_suggest,
}
DISPATCH_TABLE.update({cap: adapter_passthrough.handler for cap in _PASSTHROUGH_CAPS})


def lookup(skill_id: str) -> Handler | None:
    return DISPATCH_TABLE.get(skill_id)
