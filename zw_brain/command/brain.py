from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
import json

# Default read-side mask role. Per [2026-05-06] sensitive-field policy: business-
# visible PII (name / phone / email / id / address) is ingested raw, masked on
# read. Set ZW_BRAIN_MASK_ROLE=internal_admin to opt up (audit replay only).
import os as _os
from datetime import UTC, datetime, timedelta
from typing import Any

import zw_brain.shared.audit as audit_bus
from zw_brain.domain import policy
from zw_brain.domain.policy import DomainAccessDeniedError
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.domain.repositories.delivery import DeliveryRepository
from zw_brain.domain.repositories.external_adapter import ExternalAdapterRepository
from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
from zw_brain.domain.repositories.metadata_evidence import MetadataEvidenceRepository
from zw_brain.domain.repositories.topic_package import TopicPackageRepository, TopicPackageStateError
from zw_brain.domain.schemas import describe_schemas
from zw_brain.domain.web_snapshot_redaction import redact_webui_snapshot
from zw_brain.shared import queue
from zw_brain.shared.runtime_config import get_webui_dashboard_href
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id
from zw_brain.shared.sanitization import safe_json
from zw_brain.shared.sensitive_mask import apply_field_masks
from zw_brain.shared.state_store import StateStore
from zw_brain.skill_registration.runtime import get_manifest, load_manifests

_DEFAULT_MASK_ROLE = _os.environ.get("ZW_BRAIN_MASK_ROLE", "external")
_DEFAULT_TENANT_ID = get_runtime_tenant_id()


def _expected_iaf_issuer() -> str:
    return _os.environ.get("ZW_BRAIN_IAF_ISSUER", "")


def _expected_iaf_audience() -> str:
    return _os.environ.get("ZW_BRAIN_IAF_AUDIENCE", _os.environ.get("ZW_BRAIN_IAF_CLIENT_ID", "zw-brain"))


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _mask(payload: Any) -> Any:
    """Apply default-role mask to a serializer's outgoing payload."""
    return apply_field_masks(payload, role=_DEFAULT_MASK_ROLE)


DEFAULT_DISCOVERY_QUERY = "停车场信息"


class BrainServiceError(RuntimeError):
    pass


class UnknownSkillError(BrainServiceError):
    pass


class AccessDeniedError(BrainServiceError):
    pass


class ConfirmationRequiredError(BrainServiceError):
    pass


class InvalidStateError(BrainServiceError):
    pass


class NotFoundError(BrainServiceError):
    pass


class InvalidTokenError(BrainServiceError):
    pass


class BrainService:
    def __init__(self, state_store: StateStore | None = None) -> None:
        self._state_store = state_store or StateStore()
        self._snapshot = self._state_store.load()
        self._ui_state = {
            "role": "r1",
            "discoveryQuery": DEFAULT_DISCOVERY_QUERY,
            "brainOutage": False,
        }
        self._sync_state_views()
        self._persist()
        if self._state_store.database_store is not None:
            self._sync_reference_tables()

    def snapshot(self) -> dict[str, Any]:
        state = copy.deepcopy(self._snapshot)
        state["state"] = copy.deepcopy(self._ui_state)
        state["webui"] = {
            "dashboardHref": get_webui_dashboard_href(),
            "deploymentLabel": _os.environ.get("ZW_BRAIN_DEPLOYMENT_LABEL", "").strip(),
        }
        return state

    def manifests(self) -> dict[str, dict[str, Any]]:
        return load_manifests()

    @staticmethod
    def _validate_required_input(skill_id: str, manifest: dict[str, Any], payload: dict[str, Any]) -> None:
        # JSON Schema "required" = key presence; value-shape constraints belong elsewhere.
        # `confirmed` is intentionally skipped: it's a control signal whose absence is handled
        # by _enforce_manifest_policy (human_confirmation_required → ConfirmationRequiredError
        # → HTTP 409), not a 400 missing-field error.
        required = [
            k for k in ((manifest.get("input_schema") or {}).get("required") or [])
            if k != "confirmed"
        ]
        missing = [k for k in required if k not in payload]
        if missing:
            raise BrainServiceError(
                f"missing required input field(s): {', '.join(missing)} (skill: {skill_id})"
            )

    def invoke_skill(self, skill_id: str, payload: dict[str, Any] | None = None) -> Any:
        payload = payload or {}
        try:
            manifest = get_manifest(skill_id)
        except KeyError as exc:
            raise UnknownSkillError(skill_id) from exc
        self._validate_required_input(skill_id, manifest, payload)
        role = self._resolve_role(payload)
        self._ui_state["role"] = role
        self._enforce_manifest_policy(skill_id, manifest, role, payload)
        if manifest.get("audit_required") and not manifest.get("side_effects"):
            return self._invoke_traced_read(skill_id, role, payload, lambda: self._dispatch_skill(skill_id, payload))
        return self._dispatch_skill(skill_id, payload)

    def _dispatch_skill(self, skill_id: str, payload: dict[str, Any]) -> Any:
        match skill_id:
            case "data.search":
                return self.search_resources(str(payload.get("query", "")), int(payload.get("page", 1)))
            case "workbench.view":
                return self.get_workbench(str(payload.get("role", self._ui_state["role"])))
            case "catalog.resource_view":
                return self.get_resource(str(payload["resource_id"]))
            case "request.list":
                return {"items": self.list_requests()}

            case "request.view":
                return self.get_request(str(payload["request_id"]))
            case "approval.view":
                return self.get_approval(str(payload["request_id"]))
            case "delivery.view":
                return self.get_delivery_task(str(payload["task_id"]))
            case "delivery.list":
                return {"items": self.list_delivery_tasks()}
            case "provider.view":
                return self.get_provider_view()
            case "governance.dispute_list":
                return self.list_governance_disputes()
            case "governance.dispute_view":
                return self.get_dispute(str(payload["dispute_id"]))
            case "objection.case.create":
                return self.create_objection_case(payload)
            case "objection.case.submit":
                return self.transition_objection_case(str(payload["objection_id"]), "submitted", "submit", "提交异议", payload)
            case "objection.case.accept":
                return self.transition_objection_case(str(payload["objection_id"]), "accepted", "accept", "受理异议", payload)
            case "objection.case.reject":
                return self.transition_objection_case(str(payload["objection_id"]), "rejected", "reject", "驳回异议", payload)
            case "objection.case.assign":
                target_status = str(payload.get("target_status", "provider_investigating"))
                return self.transition_objection_case(str(payload["objection_id"]), target_status, "assign", "分发核查", payload)
            case "objection.case.reply":
                return self.reply_objection_case(payload)
            case "objection.case.review":
                decision = str(payload["decision"])
                next_status = "resolved" if decision == "resolve" else "provider_investigating"
                return self.transition_objection_case(str(payload["objection_id"]), next_status, "review", "复核异议", payload)
            case "objection.case.evaluate":
                return self.evaluate_objection_case(payload)
            case "objection.case.escalate":
                return self.transition_objection_case(str(payload["objection_id"]), "escalated", "escalate", "升级督办", {"action_result": "escalated"} | payload)
            case "objection.case.close":
                return self.transition_objection_case(str(payload["objection_id"]), "closed", "close", "关闭异议", payload)
            case "objection.case.query":
                return self.query_objection_cases(status=payload.get("status"), target_type=payload.get("target_type"))
            case "objection.process.query":
                return self.query_objection_process(str(payload["objection_id"]))
            case "objection.metric.query":
                return self.query_objection_metrics()
            case (
                "adapter.national.catalog.pull"
                | "adapter.national.resource.pull"
                | "adapter.national.catalog.report"
                | "adapter.national.resource.report"
                | "adapter.national.application.submit"
                | "adapter.national.application.receive"
                | "adapter.national.application.reconcile"
                | "adapter.national.delivery.receipt.sync"
                | "adapter.national.objection.sync"
                | "adapter.national.topic.report"
                | "adapter.cascade.consume"
                | "adapter.cascade.replay"
            ):
                return self.record_adapter_operation(skill_id, payload)
            case "delivery.receipt.ingest":
                return self.ingest_delivery_receipt(payload)
            case "ops.exchange.statistics.query":
                return self.query_exchange_statistics(
                    metric_scope=payload.get("metric_scope"),
                    resource_code=payload.get("resource_code"),
                    delivery_code=payload.get("delivery_code"),
                )
            case "ops.exchange.diagnose":
                return self.diagnose_exchange(task_id=payload.get("task_id"), attempt_id=payload.get("attempt_id"))
            case "delivery.exchange.plan":
                return self.plan_delivery_exchange(payload)
            case "delivery.exchange.start":
                return self.start_delivery_exchange(payload)
            case "delivery.exchange.publish":
                return self.publish_delivery_exchange(payload)
            case "delivery.exchange.stop":
                return self.stop_delivery_exchange(payload)
            case "application.grant.approve":
                return self.approve_application_grant(payload)
            case "application.grant.renew":
                return self.renew_application_grant(payload)
            case "require.intent.submit":
                return self.submit_requirement_intent(payload)
            case "require.intent.refine":
                return self.refine_requirement_intent(payload)
            case "require.intent.review":
                return self.review_requirement_intent(payload)
            case "require.resource.match":
                return self.match_requirement_resource(payload)
            case "delivery.subscription.manage":
                return self.manage_delivery_subscription(payload)
            case "adapter.health.probe":
                return self.record_adapter_operation(skill_id, {"adapter_slug": payload.get("adapter_slug", "adapter-health"), "operation": "health_probe", "direction": "inbound"} | payload)
            case "compliance.signal.ingest" | "risk.event.ingest" | "standard.asset.sync" | "standard.asset.recommend" | "security.scan.result.sync":
                return self.record_adapter_operation(skill_id, payload)
            case "compliance.rule.configure":
                return self.configure_compliance_rule(payload)
            case "compliance.case.open":
                return self.open_compliance_case(payload)
            case "compliance.case.assign":
                return self.transition_compliance_case(str(payload["case_id"]), "assigned", "assign", payload)
            case "compliance.case.resolve":
                return self.transition_compliance_case(str(payload["case_id"]), "resolved", "resolve", payload)
            case "compliance.case.close":
                return self.transition_compliance_case(str(payload["case_id"]), "closed", "close", payload)
            case "compliance.case.query":
                return self.query_compliance_cases(status=payload.get("status"), severity=payload.get("severity"))
            case "compliance.metric.query":
                return self.query_compliance_metrics()
            case "dashboard.compliance.query":
                return self.query_compliance_dashboard()
            case "adapter.cascade.health.query":
                return self.query_adapter_health(adapter_slug=payload.get("adapter_slug"))
            case "adapter.external.mapping.query":
                return self.query_external_mappings(
                    external_system=payload.get("external_system"),
                    local_aggregate_type=payload.get("local_aggregate_type"),
                    local_aggregate_id=payload.get("local_aggregate_id"),
                    status=payload.get("status"),
                )
            case "governance.iam_overview":
                return self.get_governance_iam_overview(payload)
            case "tenant.policy.evaluate":
                return self.evaluate_tenant_policy(payload)
            case "org.projection.sync":
                return self.sync_org_projection(payload)
            case "actor.projection.sync":
                return self.sync_actor_projection(payload)
            case "legacy.bsp.mapping.import":
                return self.import_legacy_bsp_mapping(payload)
            case "topic.package.create":
                return self.create_topic_package(payload)
            case "topic.package.configure":
                return self.configure_topic_package(payload)
            case "topic.package.submit":
                return self.transition_topic_package(str(payload["package_code"]), "submitted", "submit", payload)
            case "topic.package.review":
                decision = str(payload["decision"])
                return self.transition_topic_package(str(payload["package_code"]), "published" if decision == "approve" else "rejected", "review", payload)
            case "topic.package.publish":
                return self.transition_topic_package(str(payload["package_code"]), "published", "publish", payload)
            case "topic.package.policy.update":
                return self.update_topic_package_policy(payload)
            case "topic.package.subscribe":
                return self.subscribe_topic_package(payload)
            case "topic.package.evidence.attach":
                return self.attach_topic_package_evidence(payload)
            case "topic.package.query":
                return self.query_topic_packages(package_code=payload.get("package_code"), status=payload.get("status"))
            case "topic.package.metric.query":
                return self.query_topic_package_metrics(package_code=payload.get("package_code"))
            case "legacy.sharezone.mapping.import":
                return self.import_legacy_sharezone_mapping(payload)
            case "audit.replay_evidence_chain":
                return self.replay_evidence_chain(str(payload["dispute_id"]))
            case "zone.list":
                return {"items": self.list_zones()}
            case "zone.view":
                return self.get_zone(str(payload["zone_id"]))
            case "package.list":
                return {"items": self.list_packages()}

            case "package.view":
                return self.get_package(str(payload["package_id"]))
            case "audit.list":
                return {
                    "items": self.list_audit_events(),
                    "summary": copy.deepcopy(self._snapshot["audit_ai"]),
                }
            case "dashboard.render_command_center":
                return self.get_dashboard()
            case "catalog.group.query":
                return self.query_catalog_groups()
            case "catalog.share_zone.query":
                return self.query_catalog_share_zones()
            case "catalog.model.query":
                return self.query_catalog_models(model_code=payload.get("model_code"))
            case "catalog.model.field.query":
                return self.query_catalog_model_fields(str(payload["model_code"]))
            case "catalog.entry.query":
                return self.query_catalog_entries(query=payload.get("query"), catalog_code=payload.get("catalog_code"))
            case "catalog.browse":
                return self.browse_catalog_entries(
                    page=payload.get("page"),
                    limit=payload.get("limit"),
                    lifecycle=payload.get("lifecycle"),
                    kind=payload.get("kind"),
                    owner_org_id=payload.get("owner_org_id"),
                    query=payload.get("query"),
                )
            case "resource.asset.query":
                return self.query_resource_assets(resource_code=payload.get("resource_code"))
            case "application.resource.submit":
                return self.create_request(
                    str(payload["resource_id"]),
                    str(payload.get("role", self._ui_state["role"])),
                    bool(payload.get("confirmed")),
                    str(payload.get("query", self._ui_state.get("discoveryQuery", ""))),
                    "application.resource.submit",
                )
            case "application.resource.review":
                return self.review_request(
                    str(payload["request_id"]),
                    str(payload["decision"]),
                    str(payload.get("role", self._ui_state["role"])),
                    bool(payload.get("confirmed")),
                    "application.resource.review",
                )
            case "delivery.access.grant":
                return self.grant_delivery_access(
                    str(payload["task_id"]),
                    str(payload.get("role", self._ui_state["role"])),
                    bool(payload.get("confirmed")),
                )
            case "metadata.schema.query":
                return self.query_metadata_schema(resource_code=payload.get("resource_code"), binding_code=payload.get("binding_code"))
            case "metadata.catalog_item.query":
                return self.query_metadata_catalog_items(resource_code=payload.get("resource_code"), catalog_code=payload.get("catalog_code"))
            case "metadata.lineage.query":
                return self.query_metadata_lineage(resource_code=payload.get("resource_code"), relation_scope=payload.get("relation_scope"))
            case "metadata.gather.evidence.query":
                return self.query_metadata_gather_evidence(resource_code=payload.get("resource_code"), status=payload.get("status"))
            case "ops.catalog.quality.query":
                return self.query_catalog_quality(target_type=payload.get("target_type"), target_ref=payload.get("target_ref"))
            case "ops.catalog.statistics.query":
                return self.query_catalog_statistics()
            case "ops.service.invocation.query":
                return self.query_service_invocations(
                    resource_code=payload.get("resource_code"),
                    capability_id=payload.get("capability_id"),
                    metric_scope=payload.get("metric_scope"),
                )
            case "ops.service.report.query":
                return self.query_service_report()
            case "ops.gateway.heartbeat.ingest":
                return self.ingest_gateway_heartbeat(payload)
            case "ops.gateway.log.anchor":
                return self.anchor_gateway_log(payload)
            case "catalog.model.upsert":
                return self.upsert_catalog_model(payload)
            case "catalog.schema.mapping.upsert":
                return self.upsert_catalog_schema_mapping(payload)
            case "metadata.schema.snapshot.upsert":
                return self.upsert_metadata_schema_snapshot(payload)
            case "metadata.gather.evidence.upsert":
                return self.upsert_metadata_gather_evidence(payload)
            case "metadata.lineage.upsert":
                return self.upsert_metadata_lineage(payload)
            case "ops.catalog.quality.upsert":
                return self.upsert_catalog_quality_evidence(payload)
            case "catalog.entry.create":
                return self.create_catalog_entry_draft(payload)
            case "catalog.entry.update":
                return self.update_catalog_entry(payload)
            case "catalog.entry.create_draft":
                return self.create_catalog_entry_draft(payload)
            case "catalog.entry.submit_review":
                return self.submit_catalog_entry_review(str(payload["catalog_code"]), str(payload.get("role", self._ui_state["role"])), bool(payload.get("confirmed")))
            case "catalog.entry.review":
                return self.review_catalog_entry(str(payload["catalog_code"]), str(payload["decision"]), str(payload.get("role", self._ui_state["role"])), bool(payload.get("confirmed")))
            case "catalog.entry.publish":
                return self.transition_catalog_entry(str(payload["catalog_code"]), "active", "catalog.entry.publish", str(payload.get("role", self._ui_state["role"])), bool(payload.get("confirmed")))
            case "catalog.entry.withdraw":
                return self.transition_catalog_entry(str(payload["catalog_code"]), "retired", "catalog.entry.withdraw", str(payload.get("role", self._ui_state["role"])), bool(payload.get("confirmed")))
            case "catalog.resource.bind":
                return self.bind_catalog_resource(payload)
            case "resource.asset.submit_review":
                return self.submit_api_resource_review(str(payload["resource_code"]), str(payload.get("role", self._ui_state["role"])), bool(payload.get("confirmed")), "resource.asset.submit_review")
            case "resource.asset.review":
                return self.review_api_resource(str(payload["resource_code"]), str(payload["decision"]), str(payload.get("role", self._ui_state["role"])), bool(payload.get("confirmed")), "resource.asset.review")
            case "resource.asset.publish":
                return self.transition_api_resource(str(payload["resource_code"]), "active", "resource.asset.publish", str(payload.get("role", self._ui_state["role"])), bool(payload.get("confirmed")))
            case "resource.api.register":
                return self.register_api_resource(payload)
            case "resource.api.change":
                return self.change_api_resource(payload)
            case "resource.api.submit_review":
                return self.submit_api_resource_review(str(payload["resource_code"]), str(payload.get("role", self._ui_state["role"])), bool(payload.get("confirmed")))
            case "resource.api.review":
                return self.review_api_resource(str(payload["resource_code"]), str(payload["decision"]), str(payload.get("role", self._ui_state["role"])), bool(payload.get("confirmed")))
            case "resource.api.publish":
                return self.transition_api_resource(str(payload["resource_code"]), "active", "resource.api.publish", str(payload.get("role", self._ui_state["role"])), bool(payload.get("confirmed")))
            case "resource.api.withdraw":
                return self.transition_api_resource(str(payload["resource_code"]), "retired", "resource.api.withdraw", str(payload.get("role", self._ui_state["role"])), bool(payload.get("confirmed")))
            case "resource.api.revoke":
                return self.transition_api_resource(str(payload["resource_code"]), "revoked", "resource.api.revoke", str(payload.get("role", self._ui_state["role"])), bool(payload.get("confirmed")))
            case "resource.api.test":
                return self.test_api_resource(payload)
            case "resource.api.policy.update":
                return self.update_api_resource_policy(payload)
            case "system.snapshot":
                return redact_webui_snapshot(self.snapshot(), str(self._ui_state.get("role", "r1")))
            case "system.schema_info":
                return {"schemas": describe_schemas()}
            case "system.toggle_outage":
                return self.toggle_outage(str(payload.get("role", self._ui_state["role"])), bool(payload.get("confirmed")))
            case "request.create":
                return self.create_request(
                    str(payload["resource_id"]),
                    str(payload.get("role", self._ui_state["role"])),
                    bool(payload.get("confirmed")),
                    str(payload.get("query", self._ui_state.get("discoveryQuery", ""))),
                )
            case "request.submit":
                return self.submit_request(str(payload["request_id"]), str(payload.get("role", self._ui_state["role"])), bool(payload.get("confirmed")))
            case "approval.case.decide":
                return self.review_request(
                    str(payload["request_id"]),
                    str(payload["decision"]),
                    str(payload.get("role", self._ui_state["role"])),
                    bool(payload.get("confirmed")),
                    "approval.case.decide",
                )
            case "approval.review_decide":
                return self.review_request(
                    str(payload["request_id"]),
                    str(payload["decision"]),
                    str(payload.get("role", self._ui_state["role"])),
                    bool(payload.get("confirmed")),
                )
            case "supplement.submit":
                return self.submit_supplement(str(payload["request_id"]), str(payload.get("role", self._ui_state["role"])), bool(payload.get("confirmed")))
            case "summary.confirm":
                return self.confirm_summary(str(payload["request_id"]), str(payload.get("role", self._ui_state["role"])), bool(payload.get("confirmed")))
            case "backflow.confirm":
                return self.confirm_backflow(str(payload["task_id"]), str(payload.get("role", self._ui_state["role"])), bool(payload.get("confirmed")))
            case "delivery.reconcile_receipt":
                return self.reconcile_delivery_receipt(
                    str(payload["task_id"]),
                    str(payload.get("role", self._ui_state["role"])),
                    bool(payload.get("confirmed")),
                )
            case "service.publish_or_suspend":
                return self.publish_or_suspend_service(
                    str(payload["service_id"]),
                    str(payload["action"]),
                    str(payload.get("role", self._ui_state["role"])),
                    bool(payload.get("confirmed")),
                )
            case "capability.package.register":
                return self.register_capability_package(payload)
            case "capability.version.submit":
                return self.register_package_version(
                    str(payload["package_id"]),
                    str(payload.get("role", self._ui_state["role"])),
                    bool(payload.get("confirmed")),
                    "capability.version.submit",
                )
            case "capability.version.review":
                return self.review_package(
                    str(payload["package_id"]),
                    str(payload["decision"]),
                    str(payload.get("role", self._ui_state["role"])),
                    bool(payload.get("confirmed")),
                    "capability.version.review",
                )
            case "capability.exposure.configure":
                return self.configure_package_exposure(
                    str(payload["package_id"]),
                    str(payload["mode"]),
                    str(payload.get("role", self._ui_state["role"])),
                    bool(payload.get("confirmed")),
                    "capability.exposure.configure",
                )
            case "tenant.capability.enable":
                return self.apply_package_tenant_policy(
                    str(payload["package_id"]),
                    str(payload.get("role", self._ui_state["role"])),
                    bool(payload.get("confirmed")),
                    "tenant.capability.enable",
                    str(payload.get("tenant_id", _DEFAULT_TENANT_ID)),
                )
            case "tenant.capability.disable":
                return self.disable_tenant_capability(
                    str(payload["package_id"]),
                    str(payload.get("role", self._ui_state["role"])),
                    bool(payload.get("confirmed")),
                    str(payload.get("tenant_id", _DEFAULT_TENANT_ID)),
                )
            case "registry.artifact.export":
                return self.export_registry_artifacts()
            case "package.register_version":
                return self.register_package_version(
                    str(payload["package_id"]),
                    str(payload.get("role", self._ui_state["role"])),
                    bool(payload.get("confirmed")),
                )
            case "package.apply_tenant_policy":
                return self.apply_package_tenant_policy(
                    str(payload["package_id"]),
                    str(payload.get("role", self._ui_state["role"])),
                    bool(payload.get("confirmed")),
                    tenant_id=str(payload.get("tenant_id", _DEFAULT_TENANT_ID)),
                )
            case "package.review_decide":
                return self.review_package(
                    str(payload["package_id"]),
                    str(payload["decision"]),
                    str(payload.get("role", self._ui_state["role"])),
                    bool(payload.get("confirmed")),
                )
            case "delivery.trigger_recovery":
                return self.trigger_delivery_recovery(
                    str(payload["task_id"]),
                    str(payload.get("role", self._ui_state["role"])),
                    bool(payload.get("confirmed")),
                )
            case "package.configure_exposure":
                return self.configure_package_exposure(
                    str(payload["package_id"]),
                    str(payload["mode"]),
                    str(payload.get("role", self._ui_state["role"])),
                    bool(payload.get("confirmed")),
                )
            case "catalog.manage_entry":
                return self.manage_catalog_entry(
                    str(payload["catalog_id"]),
                    str(payload["action"]),
                    str(payload.get("role", self._ui_state["role"])),
                    bool(payload.get("confirmed")),
                )
            case "resource.manage_asset":
                return self.manage_resource_asset(
                    str(payload["resource_id"]),
                    str(payload["action"]),
                    str(payload.get("role", self._ui_state["role"])),
                    bool(payload.get("confirmed")),
                )
            case "zone.publish_topic_projection":
                return self.publish_zone_topic_projection(
                    str(payload["zone_id"]),
                    str(payload.get("role", self._ui_state["role"])),
                    bool(payload.get("confirmed")),
                )
            case "compliance.investigate_case":
                return self.investigate_dispute(
                    str(payload["dispute_id"]),
                    str(payload["action"]),
                    str(payload.get("role", self._ui_state["role"])),
                    bool(payload.get("confirmed")),
                )
            case _:
                raise UnknownSkillError(skill_id)

    def create_objection_case(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            repo = self._objection_repo()
            record = repo.create_case(
                payload
                | {
                    "actor_snapshot_json": {"actor": actor, "role": role},
                    "status": str(payload.get("status", "draft")),
                },
                tenant_id=_DEFAULT_TENANT_ID,
            )
            self._append_audit_feed("objection.case.create", record.id, "ok", actor)
            return self._objection_record_to_dict(record) | {"audit_id": audit_id}

        return self._mutate("objection.case.create", role, confirmed, payload, mutation)

    def transition_objection_case(self, objection_id: str, next_status: str, action_type: str, node_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            repo = self._objection_repo()
            try:
                record = repo.transition_case(
                    objection_id,
                    next_status,
                    action_type=action_type,
                    node_name=node_name,
                    action_result=str(payload.get("action_result", "pass")),
                    handler_org_id=payload.get("handler_org_id"),
                    handler_snapshot_json={"actor": actor, "role": role} | self._safe_json(payload.get("handler_snapshot_json") or {}),
                    opinion=payload.get("opinion") or payload.get("decision_reason") or payload.get("resolved_summary"),
                    resolved_summary=payload.get("resolved_summary"),
                    evidence=payload.get("evidence") or [],
                )
            except KeyError as exc:
                raise NotFoundError(objection_id) from exc
            except ValueError as exc:
                raise InvalidStateError(str(exc)) from exc
            self._append_audit_feed(f"objection.case.{action_type}", objection_id, "ok", actor)
            return self._objection_record_to_dict(record) | {"audit_id": audit_id}

        return self._mutate(f"objection.case.{action_type}", role, confirmed, {"objection_id": objection_id, "next_status": next_status} | payload, mutation)

    def reply_objection_case(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))
        objection_id = str(payload["objection_id"])

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            repo = self._objection_repo()
            try:
                record = repo.add_process(
                    objection_id,
                    node_name=str(payload.get("node_name", "提交核查回复")),
                    action_type="reply",
                    action_result=str(payload.get("action_result", "submitted")),
                    handler_org_id=payload.get("handler_org_id"),
                    handler_snapshot_json={"actor": actor, "role": role} | self._safe_json(payload.get("handler_snapshot_json") or {}),
                    opinion=payload.get("opinion"),
                    evidence=payload.get("evidence") or [],
                )
            except KeyError as exc:
                raise NotFoundError(objection_id) from exc
            self._append_audit_feed("objection.case.reply", objection_id, "ok", actor)
            return self._objection_record_to_dict(record) | {"audit_id": audit_id}

        return self._mutate("objection.case.reply", role, confirmed, payload, mutation)

    def evaluate_objection_case(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))
        objection_id = str(payload["objection_id"])

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            repo = self._objection_repo()
            try:
                evaluation = repo.evaluate_case(
                    objection_id,
                    payload | {"evaluator_snapshot_json": {"actor": actor, "role": role} | self._safe_json(payload.get("evaluator_snapshot_json") or {})},
                )
            except KeyError as exc:
                raise NotFoundError(objection_id) from exc
            except ValueError as exc:
                raise InvalidStateError(str(exc)) from exc
            self._append_audit_feed("objection.case.evaluate", objection_id, "ok", actor)
            return self._evaluation_record_to_dict(evaluation) | {"audit_id": audit_id}

        return self._mutate("objection.case.evaluate", role, confirmed, payload, mutation)

    def query_objection_cases(self, *, status: Any = None, target_type: Any = None) -> dict[str, Any]:
        records = [self._objection_record_to_dict(item) for item in self._objection_repo().list_cases(tenant_id=_DEFAULT_TENANT_ID)]
        if status:
            records = [item for item in records if item["status"] == str(status)]
        if target_type:
            records = [item for item in records if item["target_type"] == str(target_type)]
        return {"items": records, "total": len(records)}

    def query_objection_process(self, objection_id: str) -> dict[str, Any]:
        if self._objection_repo().get_case(objection_id, tenant_id=_DEFAULT_TENANT_ID) is None:
            raise NotFoundError(objection_id)
        return {
            "items": [self._process_record_to_dict(item) for item in self._objection_repo().list_processes(objection_id)],
            "evidence": [self._evidence_record_to_dict(item) for item in self._objection_repo().list_evidence(objection_id)],
        }

    def query_objection_metrics(self) -> dict[str, Any]:
        cases = [self._objection_record_to_dict(item) for item in self._objection_repo().list_cases(tenant_id=_DEFAULT_TENANT_ID)]
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

    def record_adapter_operation(self, skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            repo = self._external_adapter_repo()
            adapter_slug, operation, direction = self._adapter_operation_from_skill(skill_id, payload)
            idempotency_key = str(payload.get("idempotency_key") or self._adapter_idempotency_key(skill_id, payload))
            run = repo.upsert_run_record(
                {
                    "adapter_slug": adapter_slug,
                    "operation": operation,
                    "direction": direction,
                    "source_ref": payload.get("source_ref") or payload.get("external_object_id") or payload.get("local_aggregate_id"),
                    "idempotency_key": idempotency_key,
                    "status": payload.get("status", "succeeded"),
                    "target_count": payload.get("target_count", 1),
                    "success_count": payload.get("success_count"),
                    "failure_count": payload.get("failure_count", 0),
                    "receipt_json": payload.get("receipt_json") or payload.get("last_receipt_json") or {"skill_id": skill_id, "actor": actor},
                    "error_summary": payload.get("error_summary"),
                }
            )
            mapping = None
            if payload.get("external_object_id") or payload.get("local_aggregate_id") or payload.get("legacy_id"):
                mapping = repo.upsert_mapping(
                    {
                        "external_system": payload.get("external_system") or ("cascade_down" if skill_id.startswith("adapter.cascade") else "national_platform"),
                        "direction": direction,
                        "local_aggregate_type": payload.get("local_aggregate_type") or self._aggregate_type_from_skill(skill_id),
                        "local_aggregate_id": payload.get("local_aggregate_id") or "",
                        "legacy_table": payload.get("legacy_table"),
                        "legacy_id": payload.get("legacy_id"),
                        "external_object_type": payload.get("external_object_type") or self._aggregate_type_from_skill(skill_id),
                        "external_object_id": payload.get("external_object_id") or payload.get("legacy_id") or idempotency_key,
                        "protocol_version": payload.get("protocol_version", "v0.55"),
                        "batch_no": payload.get("batch_no"),
                        "status": payload.get("mapping_status", "mapped"),
                        "last_receipt_json": payload.get("receipt_json") or {},
                        "extra_json": payload.get("extra_json") or {},
                    }
                )
            self._append_audit_feed(skill_id, idempotency_key, "ok", actor)
            return {
                "run": self._adapter_run_record_to_dict(run),
                "mapping": self._external_mapping_record_to_dict(mapping) if mapping is not None else None,
                "audit_id": audit_id,
            }

        return self._mutate(skill_id, role, confirmed, payload, mutation)

    def configure_compliance_rule(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))
        rule_id = str(payload["rule_id"])

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            rules = self._snapshot.setdefault("compliance_rules", [])
            rule = next((item for item in rules if item.get("id") == rule_id), None)
            rule_payload = {
                "id": rule_id,
                "title": str(payload.get("title", rule_id)),
                "status": str(payload.get("status", "active")),
                "severity": str(payload.get("severity", "mid")),
                "rule_json": self._safe_json(payload.get("rule_json") or {}),
                "updatedAt": self._now_datetime(),
            }
            if rule is None:
                rules.append(rule_payload)
            else:
                rule.update(rule_payload)
            self._append_audit_feed("compliance.rule.configure", rule_id, "ok", actor)
            return {"rule_id": rule_id, "status": rule_payload["status"], "audit_id": audit_id}

        return self._mutate("compliance.rule.configure", role, confirmed, payload, mutation)

    def open_compliance_case(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))
        case_id = str(payload.get("case_id") or payload.get("dispute_id") or f"CMP-{self._new_audit_id()}")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            cases = self._snapshot.setdefault("disputes", [])
            if any(item.get("id") == case_id for item in cases):
                raise InvalidStateError("compliance case already exists")
            cases.append(
                {
                    "id": case_id,
                    "title": str(payload.get("title", case_id)),
                    "severity": str(payload.get("severity", "mid")),
                    "status": "detected",
                    "owner": str(payload.get("owner", payload.get("owner_org_id", "合规治理组"))),
                    "timeline": [
                        {
                            "time": self._now_datetime(),
                            "label": "打开合规事件",
                            "note": str(payload.get("summary", payload.get("note", "已登记合规信号并进入最小闭环。"))),
                        }
                    ],
                    "aiSummary": str(payload.get("aiSummary", payload.get("summary", "合规事件已进入 zw-brain 最小闭环，后续只沉淀证据与处置结果。"))),
                }
            )
            self._append_audit_feed("compliance.case.open", case_id, "ok", actor)
            return {"case_id": case_id, "status": "detected", "audit_id": audit_id}

        return self._mutate("compliance.case.open", role, confirmed, payload | {"case_id": case_id}, mutation)

    def transition_compliance_case(self, case_id: str, status: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))
        case = next((item for item in self._snapshot.setdefault("disputes", []) if item.get("id") == case_id), None)
        if case is None:
            raise NotFoundError(case_id)
        allowed = {
            "detected": {"assigned", "resolved"},
            "open": {"assigned", "resolved"},
            "assigned": {"resolved"},
            "escalated": {"assigned", "resolved"},
            "resolved": {"closed"},
            "closed": set(),
        }
        if status not in allowed.get(str(case.get("status", "open")), set()):
            raise InvalidStateError(f"invalid compliance transition: {case.get('status')} -> {status}")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            case["status"] = status
            if payload.get("owner") or payload.get("owner_org_id"):
                case["owner"] = str(payload.get("owner", payload.get("owner_org_id")))
            label = {"assign": "分派合规处置", "resolve": "完成合规处置", "close": "关闭合规事件"}[action]
            case.setdefault("timeline", []).append({"time": self._now_datetime(), "label": label, "note": str(payload.get("opinion", payload.get("summary", label)))})
            case["aiSummary"] = str(payload.get("aiSummary", payload.get("summary", f"合规事件已{label}，证据链保留在统一审计与快照中。")))
            self._append_audit_feed(f"compliance.case.{action}", case_id, "ok", actor)
            return {"case_id": case_id, "status": case["status"], "audit_id": audit_id}

        return self._mutate(f"compliance.case.{action}", role, confirmed, {"case_id": case_id, "status": status} | payload, mutation)

    def query_compliance_cases(self, *, status: Any = None, severity: Any = None) -> dict[str, Any]:
        cases = copy.deepcopy(self._snapshot.get("disputes", []))
        if status:
            cases = [item for item in cases if item.get("status") == str(status)]
        if severity:
            cases = [item for item in cases if item.get("severity") == str(severity)]
        return {"items": cases, "total": len(cases)}

    def query_compliance_metrics(self) -> dict[str, Any]:
        cases = self._snapshot.get("disputes", [])
        by_status: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        for item in cases:
            by_status[str(item.get("status", "unknown"))] = by_status.get(str(item.get("status", "unknown")), 0) + 1
            by_severity[str(item.get("severity", "unknown"))] = by_severity.get(str(item.get("severity", "unknown")), 0) + 1
        open_count = sum(count for status, count in by_status.items() if status not in {"resolved", "closed"})
        return {"total": len(cases), "open_count": open_count, "resolved_count": by_status.get("resolved", 0) + by_status.get("closed", 0), "by_status": by_status, "by_severity": by_severity}

    def query_compliance_dashboard(self) -> dict[str, Any]:
        metrics = self.query_compliance_metrics()
        return {"summary": metrics, "cases": self.query_compliance_cases()["items"], "adapterHealth": self.query_adapter_health()["summary"]}

    def query_adapter_health(self, *, adapter_slug: Any = None) -> dict[str, Any]:
        runs = [self._adapter_run_record_to_dict(item) for item in self._external_adapter_repo().list_run_records(tenant_id=_DEFAULT_TENANT_ID, adapter_slug=str(adapter_slug) if adapter_slug else None)]
        failures = [item for item in runs if item["status"] in {"failed", "partial"}]
        return {
            "items": runs,
            "summary": {
                "run_count": len(runs),
                "failure_count": len(failures),
                "last_status": runs[-1]["status"] if runs else "unknown",
            },
        }

    def query_external_mappings(self, **filters: Any) -> dict[str, Any]:
        mappings = [
            self._external_mapping_record_to_dict(item)
            for item in self._external_adapter_repo().list_mappings(
                external_system=str(filters["external_system"]) if filters.get("external_system") else None,
                local_aggregate_type=str(filters["local_aggregate_type"]) if filters.get("local_aggregate_type") else None,
                local_aggregate_id=str(filters["local_aggregate_id"]) if filters.get("local_aggregate_id") else None,
                status=str(filters["status"]) if filters.get("status") else None,
                tenant_id=_DEFAULT_TENANT_ID,
            )
        ]
        return {"items": mappings, "total": len(mappings)}

    def _objection_repo(self):
        store = self._state_store.database_store
        return store.objection_repo if store is not None else __import__("zw_brain.domain.repositories.objection", fromlist=["ObjectionRepository"]).ObjectionRepository()

    def _external_adapter_repo(self) -> ExternalAdapterRepository:
        store = self._state_store.database_store
        return store.external_adapter_repo if store is not None else ExternalAdapterRepository()

    def _governance_projection_repo(self) -> GovernanceProjectionRepository:
        store = self._state_store.database_store
        return store.governance_projection_repo if store is not None else GovernanceProjectionRepository()

    def _topic_package_repo(self) -> TopicPackageRepository:
        store = self._state_store.database_store
        return store.topic_package_repo if store is not None else TopicPackageRepository()

    def _capability_package_repo(self):
        store = self._state_store.database_store
        if store is not None:
            return store.capability_package_repo
        return __import__("zw_brain.domain.repositories.capability_package", fromlist=["CapabilityPackageRepository"]).CapabilityPackageRepository()

    def get_governance_iam_overview(self, payload: dict[str, Any]) -> dict[str, Any]:
        tenant_id = str(payload.get("tenant_id", _DEFAULT_TENANT_ID))
        status_filter = str(payload.get("binding_status", payload.get("status", "")) or "")
        capability_filter = str(payload.get("capability_id", payload.get("capability_slug", "")) or "")
        issue_filter = str(payload.get("issue_type", "") or "")
        repo = self._governance_projection_repo()
        store = self._state_store.database_store
        tenants = [self._tenant_projection_record_to_dict(item) for item in repo.list_tenants() if not tenant_id or item.tenant_id == tenant_id]
        orgs = [self._org_projection_record_to_dict(item) for item in repo.list_orgs(tenant_id=tenant_id)]
        regions = [self._region_projection_record_to_dict(item) for item in repo.list_regions(tenant_id=tenant_id)]
        roles = [self._role_projection_record_to_dict(item) for item in repo.list_roles(tenant_id=tenant_id)]
        raw_actors = repo.list_actors(tenant_id=tenant_id)
        actors = [self._actor_projection_record_to_dict(item) | {"actor_snapshot": self._actor_snapshot_from_projection(item, claims={})} for item in raw_actors]
        role_filter = str(payload.get("role_code", "") or "")
        actor_filter = str(payload.get("actor_id", payload.get("external_actor_id", "")) or "")
        if role_filter:
            roles = [item for item in roles if item.get("role_code") == role_filter]
        actors = [item for item in actors if self._filter_governance_actor(item, status_filter=status_filter, role_filter=role_filter, actor_filter=actor_filter)]
        policies = [self._tenant_policy_record_to_dict(item) for item in store.capability_package_repo.list_policies(tenant_id=tenant_id)] if store is not None else []
        if capability_filter:
            policies = [item for item in policies if item.get("package_slug") == capability_filter]
        candidates = [self._legacy_policy_candidate_record_to_dict(item) for item in repo.list_policy_candidates(tenant_id=tenant_id)]
        if capability_filter:
            candidates = [item for item in candidates if item.get("capability_id") == capability_filter]
        adapter_runs = [self._adapter_run_record_to_dict(item) for item in self._external_adapter_repo().list_run_records(tenant_id=tenant_id, adapter_slug="legacy.bsp.governance")]
        issues = self._governance_import_issues(adapter_runs)
        if issue_filter:
            issues = [item for item in issues if item.get("type") == issue_filter]
        audit_events = self._governance_audit_events(tenant_id=tenant_id, capability_filter=capability_filter, actor_filter=actor_filter)
        sample_actor = actors[0] if actors else None
        sample_policy = policies[0] if policies else None
        sample_org = next((item for item in orgs if sample_actor and item.get("org_code") == sample_actor.get("org_code")), orgs[0] if orgs else None)
        policy_probe = None
        if sample_policy is not None:
            actor_snapshot = copy.deepcopy(sample_actor.get("actor_snapshot")) if sample_actor else {}
            if actor_snapshot and not actor_snapshot.get("role_codes"):
                actor_snapshot["role_codes"] = list(sample_actor.get("role_codes_json") or [])
            policy_probe = self.evaluate_tenant_policy(
                {
                    "tenant_id": tenant_id,
                    "capability_id": sample_policy["package_slug"],
                    "surface": str(payload.get("surface", "api")),
                    "role": str(payload.get("role", (actor_snapshot.get("role_codes") or [self._ui_state["role"]])[0])),
                    "actor_snapshot": actor_snapshot,
                    "org_snapshot": copy.deepcopy(sample_org or {}),
                    "risk_context": self._safe_json(payload.get("risk_context") or {}),
                }
            )
        return {
            "tenant_id": tenant_id,
            "filters": {"binding_status": status_filter or None, "role_code": role_filter or None, "actor_id": actor_filter or None, "capability_id": capability_filter or None, "issue_type": issue_filter or None},
            "summary": {
                "tenant_count": len(tenants),
                "org_count": len(orgs),
                "region_count": len(regions),
                "actor_count": len(actors),
                "role_count": len(roles),
                "policy_count": len(policies),
                "issue_count": len(issues),
                "audit_count": len(audit_events),
                "binding_status_counts": _count_by(actors, "status"),
            },
            "tenants": tenants,
            "orgs": orgs,
            "regions": regions,
            "actors": actors,
            "roles": roles,
            "tenant_policies": policies,
            "legacy_policy_candidates": candidates,
            "import_issues": issues,
            "adapter_runs": adapter_runs,
            "audit_events": audit_events,
            "policy_probe": policy_probe,
        }

    def evaluate_tenant_policy(self, payload: dict[str, Any]) -> dict[str, Any]:
        tenant_id = str(payload.get("tenant_id", _DEFAULT_TENANT_ID))
        capability_id = str(payload.get("capability_id", payload.get("skill_id", payload.get("capability_slug", ""))))
        surface = str(payload.get("surface", "webui"))
        target_ref = payload.get("target_ref")
        role_code = str(payload.get("role_code", payload.get("role", self._ui_state["role"])))
        actor_snapshot = self._safe_json(payload.get("actor_snapshot") or {})
        org_snapshot = self._safe_json(payload.get("org_snapshot") or {})
        risk_context = self._safe_json(payload.get("risk_context") or {})
        requested_role_codes = [str(item) for item in payload.get("role_codes") or []]

        role_codes = sorted({role_code, *requested_role_codes, *[str(item) for item in actor_snapshot.get("role_codes") or []]})
        policy_version = "tenant-policy:v1"
        audit_class = "read-trace"
        human_confirmation_required = False
        if not capability_id:
            return {
                "tenant_id": tenant_id,
                "capability_id": capability_id,
                "surface": surface,
                "role_code": role_code,
                "role_codes": role_codes,
                "target_ref": target_ref,
                "allowed": False,
                "source": "fail_closed",
                "decision_reason": "missing_capability_id",
                "human_confirmation_required": False,
                "audit_class": audit_class,
                "policy_version": policy_version,
                "policy_status": None,
                "policy": None,
                "legacy_candidates": [],
                "actor_snapshot": actor_snapshot,
                "org_snapshot": org_snapshot,
                "risk_context": risk_context,
            }

        tenant_policy = None
        if self._state_store.database_store is not None:
            tenant_policy = self._state_store.database_store.capability_package_repo.get_policy(capability_id, tenant_id=tenant_id)

        registry_roles: list[str] = []
        for candidate_role in role_codes:
            try:
                if f"{capability_id}.execute" in policy.permissions_for_role(candidate_role):
                    registry_roles.append(candidate_role)
            except DomainAccessDeniedError:
                continue

        allowed = False
        source = "fail_closed"
        decision_reason = "missing_tenant_policy"
        policy_snapshot: dict[str, Any] | None = None

        candidates = [
            self._legacy_policy_candidate_record_to_dict(item)
            for item in self._governance_projection_repo().list_policy_candidates(tenant_id=tenant_id)
            if item.capability_id == capability_id and (item.surface is None or item.surface == surface)
        ]

        if tenant_policy is not None:
            policy_snapshot = copy.deepcopy(tenant_policy.policy_json)
            policy_version = str(policy_snapshot.get("policyVersion") or policy_snapshot.get("version") or policy_version)
            audit_class = str(policy_snapshot.get("auditClass") or audit_class)
            human_confirmation_required = bool(policy_snapshot.get("requiresHuman", False))
            exposed_surfaces = {str(item) for item in (policy_snapshot.get("exposedSurfaces") or [])}
            tenant_policy_json = policy_snapshot.get("tenantPolicy") if isinstance(policy_snapshot.get("tenantPolicy"), dict) else {}
            allowed_policy_roles = {str(item) for item in (tenant_policy_json.get("role_codes") or tenant_policy_json.get("roles") or [])}
            effective_role_codes = set(role_codes) - {"ACCOUNT_ADMIN"}
            policy_role_matched = bool(allowed_policy_roles & effective_role_codes) if allowed_policy_roles else role_code in effective_role_codes
            registry_or_policy_roles = set(registry_roles) | ({role_code} if policy_role_matched else set())
            tenant_enabled = tenant_policy.policy_status == "enabled" and bool(policy_snapshot.get("enabled", False))
            if not tenant_enabled:
                allowed = False
                source = "tenant_capability_policy"
                decision_reason = "tenant_policy_disabled"
            elif exposed_surfaces and surface not in exposed_surfaces:
                allowed = False
                source = "tenant_capability_policy"
                decision_reason = "surface_not_exposed"
            elif not registry_or_policy_roles:
                allowed = False
                source = "brain_registry"
                decision_reason = "role_not_allowed_by_registry"
            else:
                allowed = True
                source = "tenant_capability_policy"
                decision_reason = "allowed_by_tenant_policy"
        else:
            allowed = False
            source = "fail_closed"
            decision_reason = "missing_tenant_policy"

        actor_role_codes = {str(item) for item in actor_snapshot.get("role_codes") or []}
        requested_role_set = {role_code, *requested_role_codes}
        actor_status = str(
            actor_snapshot.get("status")
            or actor_snapshot.get("binding_status")
            or actor_snapshot.get("iam_binding_status")
            or ""
        ).lower()
        blocked_actor_reasons = {
            "disabled": "actor_disabled",
            "inactive": "actor_disabled",
            "unmatched": "actor_unmatched",
            "iam_account_missing": "iam_account_missing",
        }
        actor_tenant_id = str(actor_snapshot.get("tenant_id") or "")
        org_tenant_id = str(org_snapshot.get("tenant_id") or "")
        actor_org_code = str(actor_snapshot.get("org_code") or "")
        org_code = str(org_snapshot.get("org_code") or "")

        if actor_status in blocked_actor_reasons:
            allowed = False
            source = "fail_closed"
            decision_reason = blocked_actor_reasons[actor_status]
        elif actor_tenant_id and actor_tenant_id != tenant_id:
            allowed = False
            source = "fail_closed"
            decision_reason = "cross_tenant_denied"
        elif org_tenant_id and org_tenant_id != tenant_id:
            allowed = False
            source = "fail_closed"
            decision_reason = "org_tenant_mismatch"
        elif actor_org_code and org_code and actor_org_code != org_code:
            allowed = False
            source = "fail_closed"
            decision_reason = "org_binding_mismatch"
        elif allowed and actor_role_codes and role_code not in actor_role_codes:
            allowed = False
            source = "fail_closed"
            decision_reason = "role_binding_mismatch"
        elif allowed and actor_role_codes and not requested_role_set.issubset(actor_role_codes):
            non_registry_roles = requested_role_set - {role_code}
            if non_registry_roles and not non_registry_roles.issubset(actor_role_codes):
                allowed = False
                source = "fail_closed"
                decision_reason = "role_binding_mismatch"
        elif risk_context.get("cross_tenant") and tenant_id != str(actor_snapshot.get("tenant_id") or tenant_id):
            allowed = False
            source = "fail_closed"
            decision_reason = "cross_tenant_denied"
        elif risk_context.get("high_risk") or risk_context.get("requires_human") or risk_context.get("human_confirmation_required"):
            human_confirmation_required = True

        return {
            "tenant_id": tenant_id,
            "capability_id": capability_id,
            "surface": surface,
            "role_code": role_code,
            "role_codes": role_codes,
            "target_ref": target_ref,
            "allowed": allowed,
            "source": source,
            "decision_reason": decision_reason,
            "human_confirmation_required": human_confirmation_required,
            "audit_class": audit_class,
            "policy_version": policy_version,
            "policy_status": tenant_policy.policy_status if tenant_policy is not None else None,
            "policy": policy_snapshot,
            "legacy_candidates": candidates,
            "actor_snapshot": actor_snapshot,
            "org_snapshot": org_snapshot,
            "risk_context": risk_context,
        }

    def sync_org_projection(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            repo = self._governance_projection_repo()
            tenant = repo.upsert_tenant(payload.get("tenant") or payload)
            tenant_id = tenant.tenant_id
            regions = [repo.upsert_region(item, tenant_id=tenant_id) for item in payload.get("regions") or []]
            orgs_payload = payload.get("orgs") or ([payload] if payload.get("org_code") else [])
            orgs = [repo.upsert_org(item, tenant_id=tenant_id) for item in orgs_payload]
            roles = [repo.upsert_role(item, tenant_id=tenant_id) for item in payload.get("roles") or []]
            self._append_audit_feed("org.projection.sync", tenant.tenant_id, "ok", actor)
            return {
                "tenant": self._tenant_projection_record_to_dict(tenant),
                "orgs": [self._org_projection_record_to_dict(item) for item in orgs],
                "regions": [self._region_projection_record_to_dict(item) for item in regions],
                "roles": [self._role_projection_record_to_dict(item) for item in roles],
                "audit_id": audit_id,
            }

        return self._mutate("org.projection.sync", role, confirmed, payload, mutation)

    def sync_actor_projection(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            repo = self._governance_projection_repo()
            actors_payload = payload.get("actors") or [payload]
            actors: list[Any] = []
            actor_snapshots: list[dict[str, Any]] = []
            for item in actors_payload:
                actor_payload = dict(item)
                claims = actor_payload.get("iaf_claims")
                claims_payload = {}
                if claims:
                    actor_payload = actor_payload | self._build_actor_projection_from_claims(
                        claims=claims,
                        expected_state=actor_payload.get("expected_state"),
                        expected_nonce=actor_payload.get("expected_nonce"),
                        tenant_id=str(actor_payload.get("tenant_id", _DEFAULT_TENANT_ID)),
                        org_code=actor_payload.get("org_code"),
                        fallback_roles=actor_payload.get("role_codes") or actor_payload.get("iam_role_codes") or [],
                        display_name=actor_payload.get("display_name"),
                    )
                    claims_payload = actor_payload.get("iaf_claims") if isinstance(actor_payload.get("iaf_claims"), dict) else {}
                actor_record = repo.upsert_actor(actor_payload, tenant_id=str(actor_payload.get("tenant_id", _DEFAULT_TENANT_ID)))
                actors.append(actor_record)
                actor_snapshots.append(self._actor_snapshot_from_projection(actor_record, claims=claims_payload))
            self._append_audit_feed("actor.projection.sync", actors[0].external_actor_id if actors else "actor_projection", "ok", actor)
            return {
                "items": [self._actor_projection_record_to_dict(item) for item in actors],
                "actor_snapshots": actor_snapshots,
                "total": len(actors),
                "audit_id": audit_id,
            }

        return self._mutate("actor.projection.sync", role, confirmed, payload, mutation)

    def import_legacy_bsp_mapping(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))

        def _normalize_candidates(input_payload: dict[str, Any]) -> list[dict[str, Any]]:
            manifest = input_payload.get("mapping_manifest") if isinstance(input_payload.get("mapping_manifest"), dict) else {}
            manifest_version = input_payload.get("manifest_version") or manifest.get("manifest_version") or manifest.get("version") or "inline-v1"
            manifest_source_ref = input_payload.get("manifest_source_ref") or manifest.get("source_ref") or "legacy:bsp:mapping-manifest:inline-v1"
            manifest_rows = manifest.get("rows") if isinstance(manifest.get("rows"), list) else None
            source_rows = input_payload.get("candidates") or ([input_payload] if input_payload.get("legacy_permission_ref") else (manifest_rows or input_payload.get("rows") or []))
            normalized = []
            for item in source_rows:
                row = dict(item)
                normalized.append(
                    {
                        "legacy_permission_ref": str(row.get("legacy_permission_ref") or ""),
                        "legacy_role_ref": row.get("legacy_role_ref"),
                        "capability_id": str(row.get("capability_id") or ""),
                        "surface": row.get("surface"),
                        "evidence_json": row.get("evidence_json") or row.get("manifest_evidence_json") or {},
                        "candidate_status": row.get("candidate_status") or "pending_review",
                        "mapping_status": row.get("mapping_status") or "mapped",
                        "source_ref": row.get("source_ref") or f"legacy:bsp:{row.get('legacy_permission_ref') or 'unknown'}",
                        "legacy_object_ref": row.get("legacy_object_ref") or str(row.get("legacy_permission_ref") or ""),
                        "manifest_version": row.get("manifest_version") or manifest_version,
                        "manifest_source_ref": row.get("manifest_source_ref") or manifest_source_ref,
                    }
                )
            return normalized

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            mode = str(payload.get("mode", payload.get("operation", "apply"))).lower()
            if mode not in {"dry-run", "dry_run", "apply"}:
                raise BrainServiceError(f"unsupported import mode: {mode}")
            dry_run = mode in {"dry-run", "dry_run"}
            tenant_id = str(payload.get("tenant_id", _DEFAULT_TENANT_ID))
            repo = self._governance_projection_repo()
            capability_manifests = self.manifests()

            candidates_payload = _normalize_candidates(payload)
            block_issues = {"iam_account_missing": 0, "unmatched": 0, "unmapped_permission": 0}
            counters = {
                "source_count": len(candidates_payload),
                "projection_count": 0,
                "mapping_count": 0,
                "skip_count": 0,
                "failure_count": 0,
            }
            preview_items: list[dict[str, Any]] = []

            for item in candidates_payload:
                manifest_version = str(item.get("manifest_version") or "inline-v1")
                manifest_source_ref = str(item.get("manifest_source_ref") or "legacy:bsp:mapping-manifest:inline-v1")
                raw_evidence = self._safe_json(item.get("evidence_json") or {})
                reviewable_evidence = {
                    key: value
                    for key, value in raw_evidence.items()
                    if key not in {"menu_tree", "button_permission_tree", "permission_sql", "sql", "legacy_menu", "legacy_url", "route_component"}
                }
                evidence = reviewable_evidence | {
                    "manifest_version": manifest_version,
                    "manifest_source_ref": manifest_source_ref,
                }
                status = str(item.get("candidate_status") or "pending_review")
                capability_id = str(item.get("capability_id") or "")
                legacy_permission_ref = str(item.get("legacy_permission_ref") or "")
                source_ref = str(item.get("source_ref") or f"legacy:bsp:{legacy_permission_ref or 'unknown'}")
                mapping_status = str(item.get("mapping_status") or "mapped")
                skip_reason = None

                if status in {"iam_account_missing", "unmatched", "disabled"}:
                    if status == "iam_account_missing":
                        block_issues["iam_account_missing"] += 1
                    else:
                        block_issues["unmatched"] += 1
                    counters["skip_count"] += 1
                    skip_reason = status
                elif not capability_id or capability_id not in capability_manifests:
                    block_issues["unmapped_permission"] += 1
                    counters["failure_count"] += 1
                    skip_reason = "unmapped_permission"
                else:
                    counters["projection_count"] += 1
                    counters["mapping_count"] += 1
                    if not dry_run:
                        repo.import_legacy_policy_candidate(
                            {
                                "legacy_system": item.get("legacy_system") or "dsp-bsp",
                                "legacy_permission_ref": legacy_permission_ref,
                                "legacy_role_ref": item.get("legacy_role_ref"),
                                "capability_id": capability_id,
                                "surface": item.get("surface"),
                                "candidate_status": status,
                                "evidence_json": evidence,
                            },
                            tenant_id=tenant_id,
                        )
                        repo.upsert_legacy_object_mapping(
                            {
                                "source_ref": source_ref,
                                "legacy_object_ref": item.get("legacy_object_ref") or legacy_permission_ref,
                                "legacy_system": item.get("legacy_system") or "dsp-bsp",
                                "legacy_object_type": item.get("legacy_object_type") or "permission",
                                "canonical_type": "capability",
                                "canonical_ref": capability_id,
                                "mapping_status": mapping_status,
                                "evidence_json": evidence,
                            },
                            tenant_id=tenant_id,
                        )

                preview_items.append(
                    {
                        "legacy_permission_ref": legacy_permission_ref,
                        "legacy_role_ref": item.get("legacy_role_ref"),
                        "capability_id": capability_id,
                        "surface": item.get("surface"),
                        "candidate_status": status,
                        "source_ref": source_ref,
                        "manifest_version": manifest_version,
                        "manifest_source_ref": manifest_source_ref,
                        "evidence_json": evidence,
                        "result": "skipped" if skip_reason else ("planned" if dry_run else "applied"),
                        "reason": skip_reason,
                    }
                )

            self._append_audit_feed("legacy.bsp.mapping.import", "legacy_policy_mapping_candidate", "warning" if counters["failure_count"] else "ok", actor)
            return {
                "mode": "dry-run" if dry_run else "apply",
                "tenant_id": tenant_id,
                "items": preview_items,
                "total": len(preview_items),
                "audit_id": audit_id,
                "summary": counters | {"blockers": block_issues},
            }

        return self._mutate("legacy.bsp.mapping.import", role, confirmed, payload, mutation)

    def create_topic_package(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            record = self._topic_package_repo().create_package(payload | {"actor_snapshot_json": {"actor": actor, "role": role}})
            self._append_audit_feed("topic.package.create", record.package_code, "ok", actor)
            return self._topic_package_record_to_dict(record) | {"audit_id": audit_id}

        return self._mutate("topic.package.create", role, confirmed, payload, mutation)

    def configure_topic_package(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))
        package_code = str(payload["package_code"])

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            try:
                record = self._topic_package_repo().configure_package(package_code, payload | {"actor_snapshot_json": {"actor": actor, "role": role}})
            except KeyError as exc:
                raise NotFoundError(package_code) from exc
            self._append_audit_feed("topic.package.configure", package_code, "ok", actor)
            return self._topic_package_record_to_dict(record) | {"audit_id": audit_id}

        return self._mutate("topic.package.configure", role, confirmed, payload, mutation)

    def transition_topic_package(self, package_code: str, next_status: str, action_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            try:
                record = self._topic_package_repo().transition_package(
                    package_code,
                    next_status,
                    payload | {"action_type": action_type, "actor_snapshot_json": {"actor": actor, "role": role}},
                )
            except KeyError as exc:
                raise NotFoundError(package_code) from exc
            except TopicPackageStateError as exc:
                raise InvalidStateError(str(exc)) from exc
            self._append_audit_feed(f"topic.package.{action_type}", package_code, "ok", actor)
            return self._topic_package_record_to_dict(record) | {"audit_id": audit_id}

        return self._mutate(f"topic.package.{action_type}", role, confirmed, {"package_code": package_code, "next_status": next_status} | payload, mutation)

    def update_topic_package_policy(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))
        package_code = str(payload["package_code"])

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            try:
                records = self._topic_package_repo().update_policy(package_code, payload | {"actor_snapshot_json": {"actor": actor, "role": role}})
            except KeyError as exc:
                raise NotFoundError(package_code) from exc
            self._append_audit_feed("topic.package.policy.update", package_code, "ok", actor)
            return {"items": [self._topic_visibility_record_to_dict(item) for item in records], "total": len(records), "audit_id": audit_id}

        return self._mutate("topic.package.policy.update", role, confirmed, payload, mutation)

    def subscribe_topic_package(self, payload: dict[str, Any]) -> dict[str, Any]:
        subscription = {
            "visibility_code": str(payload.get("visibility_code") or f"{payload.get('org_code', '*')}:{payload.get('role_code', '*')}:subscription:use"),
            "org_code": payload.get("org_code"),
            "role_code": payload.get("role_code"),
            "region_code": payload.get("region_code"),
            "surface": "subscription",
            "intent": "use",
            "policy_status": str(payload.get("policy_status", "pending_review")),
            "condition_json": payload.get("condition_json") or payload.get("condition") or {},
        }
        return self.update_topic_package_policy(payload | {"visibility": [subscription]})

    def attach_topic_package_evidence(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))
        package_code = str(payload["package_code"])

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            try:
                record = self._topic_package_repo().attach_evidence(package_code, payload | {"actor_snapshot_json": {"actor": actor, "role": role}})
            except KeyError as exc:
                raise NotFoundError(package_code) from exc
            self._append_audit_feed("topic.package.evidence.attach", package_code, "ok", actor)
            return self._topic_evidence_record_to_dict(record) | {"audit_id": audit_id}

        return self._mutate("topic.package.evidence.attach", role, confirmed, payload, mutation)

    def query_topic_packages(self, *, package_code: Any = None, status: Any = None) -> dict[str, Any]:
        repo = self._topic_package_repo()
        if package_code:
            record = repo.get_package(str(package_code), tenant_id=_DEFAULT_TENANT_ID)
            if record is None:
                raise NotFoundError(str(package_code))
            items = [self._topic_package_detail_to_dict(record)]
        else:
            items = [self._topic_package_record_to_dict(item) for item in repo.list_packages(tenant_id=_DEFAULT_TENANT_ID, status=str(status) if status else None)]
        return {"items": items, "total": len(items)}

    def query_topic_package_metrics(self, *, package_code: Any = None) -> dict[str, Any]:
        repo = self._topic_package_repo()
        packages = [repo.get_package(str(package_code))] if package_code else repo.list_packages()
        packages = [item for item in packages if item is not None]
        metrics = []
        for package in packages:
            metrics.extend(self._topic_metric_record_to_dict(item) for item in repo.list_metrics(package.package_code))
        return {
            "items": metrics,
            "summary": {
                "package_count": len(packages),
                "published_count": sum(1 for item in packages if item.status == "published"),
                "metric_count": len(metrics),
            },
        }

    def import_legacy_sharezone_mapping(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            record = self._topic_package_repo().import_legacy_sharezone(payload | {"actor_snapshot_json": {"actor": actor, "role": role}})
            self._append_audit_feed("legacy.sharezone.mapping.import", record.package_code, "ok", actor)
            return self._topic_package_record_to_dict(record) | {"audit_id": audit_id}

        return self._mutate("legacy.sharezone.mapping.import", role, confirmed, payload, mutation)

    def _filter_governance_actor(self, item: dict[str, Any], *, status_filter: str, role_filter: str, actor_filter: str) -> bool:
        profile = item.get("profile_json") if isinstance(item.get("profile_json"), dict) else {}
        if status_filter and item.get("status") != status_filter and profile.get("binding_status") != status_filter:
            return False
        if role_filter and role_filter not in (item.get("role_codes_json") or []):
            return False
        if actor_filter and item.get("external_actor_id") != actor_filter:
            return False
        return True

    def _tenant_projection_record_to_dict(self, item: Any) -> dict[str, Any]:
        return {"tenant_id": item.tenant_id, "tenant_name": item.tenant_name, "status": item.status, "source_ref": item.source_ref, "profile_json": copy.deepcopy(item.profile_json)}

    def _org_projection_record_to_dict(self, item: Any) -> dict[str, Any]:
        return {"org_code": item.org_code, "org_name": item.org_name, "parent_org_code": item.parent_org_code, "region_code": item.region_code, "status": item.status, "source_ref": item.source_ref, "profile_json": copy.deepcopy(item.profile_json)}

    def _region_projection_record_to_dict(self, item: Any) -> dict[str, Any]:
        return {"region_code": item.region_code, "region_name": item.region_name, "parent_region_code": item.parent_region_code, "region_level": item.region_level, "status": item.status, "source_ref": item.source_ref, "profile_json": copy.deepcopy(item.profile_json)}

    def _role_projection_record_to_dict(self, item: Any) -> dict[str, Any]:
        return {"role_code": item.role_code, "role_name": item.role_name, "status": item.status, "source_ref": item.source_ref, "profile_json": copy.deepcopy(item.profile_json)}

    def _actor_projection_record_to_dict(self, item: Any) -> dict[str, Any]:
        # display_name + profile_json may carry person names / phone / email /
        # id_card / address — mask before egress per [2026-05-06] policy.
        return _mask({"external_actor_id": item.external_actor_id, "display_name": item.display_name, "org_code": item.org_code, "role_codes_json": copy.deepcopy(item.role_codes_json), "status": item.status, "source_ref": item.source_ref, "profile_json": copy.deepcopy(item.profile_json)})

    def _legacy_policy_candidate_record_to_dict(self, item: Any) -> dict[str, Any]:
        return {"legacy_system": item.legacy_system, "legacy_permission_ref": item.legacy_permission_ref, "legacy_role_ref": item.legacy_role_ref, "capability_id": item.capability_id, "surface": item.surface, "candidate_status": item.candidate_status, "evidence_json": copy.deepcopy(item.evidence_json)}

    def _tenant_policy_record_to_dict(self, item: Any) -> dict[str, Any]:
        return {"tenant_id": item.tenant_id, "package_slug": item.package_slug, "policy_status": item.policy_status, "policy_json": copy.deepcopy(item.policy_json)}

    def _governance_import_issues(self, adapter_runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        for run in adapter_runs:
            receipt = run.get("receipt_json") if isinstance(run.get("receipt_json"), dict) else {}
            for issue in receipt.get("issues") or []:
                if not isinstance(issue, dict):
                    continue
                issues.append(copy.deepcopy(issue) | {"adapter_run_id": run.get("id"), "adapter_status": run.get("status"), "source_ref": run.get("source_ref")})
        store = self._state_store.database_store
        if store is not None:
            for call in store.list_capability_calls():
                if call.skill_id != "legacy.bsp.mapping.import":
                    continue
                for item in call.output_json.get("items") or []:
                    if isinstance(item, dict) and item.get("reason"):
                        issues.append({"type": item["reason"], "table": "legacy.bsp.mapping.import", "legacy_ref": item.get("legacy_permission_ref"), "detail": {"legacy_role_ref": item.get("legacy_role_ref"), "capability_id": item.get("capability_id")}, "capability_call_ref": call.call_ref})
        return issues

    def _governance_audit_events(self, *, tenant_id: str, capability_filter: str = "", actor_filter: str = "") -> list[dict[str, Any]]:
        store = self._state_store.database_store
        if store is None:
            return []
        events = []
        for item in store.list_audit_events():
            payload = item.payload_json if isinstance(item.payload_json, dict) else {}
            if payload.get("tenant_id") not in {None, "", tenant_id}:
                continue
            if capability_filter and payload.get("capability_id") != capability_filter and payload.get("capability_slug") != capability_filter:
                continue
            if actor_filter and actor_filter not in {str(payload.get("external_actor_id", "")), str(payload.get("actor_id", "")), str(payload.get("actor_snapshot", {}).get("subject", "")) if isinstance(payload.get("actor_snapshot"), dict) else ""}:
                continue
            if item.skill_id in {"tenant.policy.evaluate", "legacy.bsp.mapping.import", "org.projection.sync", "actor.projection.sync", "governance.iam_overview"}:
                events.append({"id": item.request_id, "skill_id": item.skill_id, "phase": item.phase, "actor": item.actor, "occurred_at": item.occurred_at.isoformat(), "payload_json": copy.deepcopy(payload)})
        return events

    def _topic_package_record_to_dict(self, item: Any) -> dict[str, Any]:
        # display_snapshot_json.contacts may carry contact_name + contact_phone
        # for the case's personally-named contacts — mask before egress.
        return _mask({"package_code": item.package_code, "title": item.title, "scenario": item.scenario, "owner_org_id": item.owner_org_id, "owner_org_snapshot_json": copy.deepcopy(item.owner_org_snapshot_json), "status": item.status, "display_snapshot_json": copy.deepcopy(item.display_snapshot_json), "metric_snapshot_json": copy.deepcopy(item.metric_snapshot_json), "source_ref": item.source_ref})

    def _topic_package_detail_to_dict(self, item: Any) -> dict[str, Any]:
        repo = self._topic_package_repo()
        return self._topic_package_record_to_dict(item) | {
            "items": [self._topic_item_record_to_dict(record) for record in repo.list_items(item.package_code, tenant_id=_DEFAULT_TENANT_ID)],
            "visibility": [self._topic_visibility_record_to_dict(record) for record in repo.list_visibility(item.package_code)],
            "reviews": [self._topic_review_record_to_dict(record) for record in repo.list_review_records(item.package_code)],
            "evidence": [self._topic_evidence_record_to_dict(record) for record in repo.list_evidence(item.package_code)],
            "metrics": [self._topic_metric_record_to_dict(record) for record in repo.list_metrics(item.package_code)],
        }

    def _topic_item_record_to_dict(self, item: Any) -> dict[str, Any]:
        return {"item_code": item.item_code, "ref_type": item.ref_type, "ref_id": item.ref_id, "ref_status": item.ref_status, "title": item.title, "display_order": item.display_order, "summary_json": copy.deepcopy(item.summary_json)}

    def _topic_visibility_record_to_dict(self, item: Any) -> dict[str, Any]:
        return {"visibility_code": item.visibility_code, "org_code": item.org_code, "role_code": item.role_code, "region_code": item.region_code, "surface": item.surface, "intent": item.intent, "policy_status": item.policy_status, "condition_json": copy.deepcopy(item.condition_json)}

    def _topic_review_record_to_dict(self, item: Any) -> dict[str, Any]:
        return {"action_type": item.action_type, "action_result": item.action_result, "from_status": item.from_status, "to_status": item.to_status, "reviewer_snapshot_json": copy.deepcopy(item.reviewer_snapshot_json), "opinion": item.opinion, "evidence_json": copy.deepcopy(item.evidence_json), "created_at": item.created_at.isoformat()}

    def _topic_evidence_record_to_dict(self, item: Any) -> dict[str, Any]:
        return {"id": item.id, "evidence_type": item.evidence_type, "title": item.title, "related_ref_type": item.related_ref_type, "related_ref_id": item.related_ref_id, "content_json": copy.deepcopy(item.content_json), "submitted_by_json": copy.deepcopy(item.submitted_by_json), "created_at": item.created_at.isoformat()}

    def _topic_metric_record_to_dict(self, item: Any) -> dict[str, Any]:
        return {"metric_key": item.metric_key, "metric_value": item.metric_value, "metric_json": copy.deepcopy(item.metric_json)}

    def _objection_record_to_dict(self, item: Any) -> dict[str, Any]:
        return {
            "id": item.id,
            "tenant_id": item.tenant_id,
            "objection_kind": item.objection_kind,
            "target_type": item.target_type,
            "target_id": item.target_id,
            "related_application_id": item.related_application_id,
            "title": item.title,
            "complainant_org_id": item.complainant_org_id,
            "provider_org_id": item.provider_org_id,
            "basis_text": item.basis_text,
            "expected_result": item.expected_result,
            "status": item.status,
            "resolved_summary": item.resolved_summary,
            "closed_at": item.closed_at.isoformat() if item.closed_at else None,
        }

    def _process_record_to_dict(self, item: Any) -> dict[str, Any]:
        # handler_snapshot_json may carry handler_name + handler_phone — mask.
        return _mask({
            "id": item.id,
            "objection_id": item.objection_id,
            "node_name": item.node_name,
            "handler_org_id": item.handler_org_id,
            "handler_snapshot_json": copy.deepcopy(item.handler_snapshot_json),
            "action_type": item.action_type,
            "action_result": item.action_result,
            "opinion": item.opinion,
            "created_at": item.created_at.isoformat(),
        })

    def _evidence_record_to_dict(self, item: Any) -> dict[str, Any]:
        return {
            "id": item.id,
            "objection_id": item.objection_id,
            "evidence_type": item.evidence_type,
            "content_json": copy.deepcopy(item.content_json),
            "submitted_by_json": copy.deepcopy(item.submitted_by_json),
            "created_at": item.created_at.isoformat(),
        }

    def _evaluation_record_to_dict(self, item: Any) -> dict[str, Any]:
        return {
            "id": item.id,
            "objection_id": item.objection_id,
            "evaluator_snapshot_json": copy.deepcopy(item.evaluator_snapshot_json),
            "solved_flag": item.solved_flag,
            "overall_score": item.overall_score,
            "timeliness_score": item.timeliness_score,
            "result_score": item.result_score,
            "comment": item.comment,
        }

    def _adapter_run_record_to_dict(self, item: Any) -> dict[str, Any]:
        return {
            "id": item.id,
            "adapter_slug": item.adapter_slug,
            "operation": item.operation,
            "direction": item.direction,
            "source_ref": item.source_ref,
            "idempotency_key": item.idempotency_key,
            "status": item.status,
            "target_count": item.target_count,
            "success_count": item.success_count,
            "failure_count": item.failure_count,
            "receipt_json": copy.deepcopy(item.receipt_json),
            "error_summary": item.error_summary,
        }

    def _external_mapping_record_to_dict(self, item: Any) -> dict[str, Any]:
        return {
            "id": item.id,
            "external_system": item.external_system,
            "direction": item.direction,
            "local_aggregate_type": item.local_aggregate_type,
            "local_aggregate_id": item.local_aggregate_id,
            "external_object_type": item.external_object_type,
            "external_object_id": item.external_object_id,
            "protocol_version": item.protocol_version,
            "batch_no": item.batch_no,
            "status": item.status,
            "last_receipt_json": copy.deepcopy(item.last_receipt_json),
        }

    def _adapter_operation_from_skill(self, skill_id: str, payload: dict[str, Any]) -> tuple[str, str, str]:
        if payload.get("adapter_slug") or payload.get("operation"):
            return str(payload.get("adapter_slug", skill_id.rsplit(".", 1)[0])), str(payload.get("operation", skill_id.rsplit(".", 1)[1])), str(payload.get("direction", "inbound"))
        if skill_id.startswith("adapter.cascade"):
            operation = "replay" if skill_id.endswith("replay") else "consume"
            return "cascade", operation, str(payload.get("direction", "inbound"))
        if skill_id.startswith("standard.asset"):
            return "standard_asset", skill_id.rsplit(".", 1)[1], str(payload.get("direction", "inbound"))
        if skill_id.startswith("security.scan"):
            return "security_scan", "result_sync", str(payload.get("direction", "inbound"))
        if skill_id.startswith("risk.event"):
            return "risk_event", "ingest", str(payload.get("direction", "inbound"))
        if skill_id.startswith("compliance.signal"):
            return "compliance_signal", "ingest", str(payload.get("direction", "inbound"))
        parts = skill_id.split(".")
        operation = parts[-1]
        if operation in {"pull", "receive", "reconcile", "sync"}:
            direction = "inbound" if operation in {"pull", "receive"} else str(payload.get("direction", "inbound"))
        else:
            direction = str(payload.get("direction", "outbound"))
        return "national", operation, direction

    def _aggregate_type_from_skill(self, skill_id: str) -> str:
        for value in ("catalog", "resource", "application", "delivery", "objection", "topic"):
            if f".{value}." in skill_id:
                return "topic_package" if value == "topic" else value
        return "external"

    def _adapter_idempotency_key(self, skill_id: str, payload: dict[str, Any]) -> str:
        return ":".join(
            [
                skill_id,
                str(payload.get("local_aggregate_type") or self._aggregate_type_from_skill(skill_id)),
                str(payload.get("local_aggregate_id") or payload.get("external_object_id") or payload.get("source_ref") or "pending"),
                str(payload.get("external_system") or "national_platform"),
            ]
        )


    def get_workbench(self, role: str) -> dict[str, Any]:
        if role not in self._snapshot["workbench"]:
            raise NotFoundError(role)
        return copy.deepcopy(self._snapshot["workbench"][role])

    def list_requests(self) -> list[dict[str, Any]]:
        items = copy.deepcopy(self._snapshot["requests"])
        store = self._state_store.database_store
        if store is None:
            return items
        records = {record.application_code: record for record in store.application_repo.list_records(tenant_id=_DEFAULT_TENANT_ID)}
        for item in items:
            record = records.get(item["id"])
            if record is not None:
                item["status"] = record.status
                item["repository"] = {
                    "application_code": record.application_code,
                    "applicant_name": record.applicant_name,
                    "applicant_org": record.applicant_org,
                }
        return items

    def list_packages(self) -> list[dict[str, Any]]:
        items = copy.deepcopy(self._snapshot["capability_packages"])
        store = self._state_store.database_store
        if store is None:
            return items
        records = {record.package_slug: record for record in store.capability_package_repo.list_packages()}
        policies = {item.package_slug: item for item in store.capability_package_repo.list_policies()}
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

    def list_audit_events(self) -> list[dict[str, Any]]:
        store = self._state_store.database_store
        if store is None:
            return copy.deepcopy(self._snapshot["audit_events"])
        return [
            {
                "id": item.request_id,
                "time": item.occurred_at.strftime("%m-%d %H:%M"),
                "actor": item.actor,
                "type": f"{item.skill_id}.{item.phase}",
                "target": self._audit_target_from_payload(item.request_id, item.payload_json),
                "result": "ok",
                "chain": "pending",
            }
            for item in store.list_audit_events()
        ]

    def list_delivery_tasks(self) -> list[dict[str, Any]]:
        tasks = copy.deepcopy(self._snapshot["delivery_tasks"])
        store = self._state_store.database_store
        if store is None:
            return tasks
        records = {record.delivery_code: record for record in store.delivery_repo.list_tasks(tenant_id=_DEFAULT_TENANT_ID)}
        receipts = {
            task_id: self.get_delivery_task(task_id).get("receipts", [])
            for task_id in [item["id"] for item in tasks]
        }
        for task in tasks:
            record = records.get(task["id"])
            if record is not None:
                task["status"] = record.state
                task["repository"] = {
                    "deliveryCode": record.delivery_code,
                    "applicationCode": record.application_code,
                    "channel": record.channel,
                }
                task["receipts"] = receipts.get(task["id"], [])
        return tasks

    def list_zones(self) -> list[dict[str, Any]]:
        zones = copy.deepcopy(self._snapshot["zones"])
        resource = self.get_resource("res-jbxx-ledger")
        for zone in zones:
            if zone["id"] == "business":
                zone["repository"] = {
                    "resourceCatalogCode": resource.get("repository", {}).get("catalogCode"),
                    "resourceLifecycleStatus": resource.get("repository", {}).get("lifecycleStatus"),
                }
        return zones

    def list_governance_disputes(self) -> dict[str, Any]:
        items = copy.deepcopy(self._snapshot["disputes"])
        store = self._state_store.database_store
        if store is not None:
            records = {record.id: record for record in store.objection_repo.list_cases(tenant_id=_DEFAULT_TENANT_ID)}
            for item in items:
                record = records.get(item["id"])
                if record is not None:
                    item["repository"] = {
                        "objectionKind": record.objection_kind,
                        "targetType": record.target_type,
                        "status": record.status,
                    }
                    evaluation = store.objection_repo.get_evaluation(item["id"])
                    if evaluation is not None:
                        item["evaluation"] = {
                            "solvedFlag": evaluation.solved_flag,
                            "overallScore": evaluation.overall_score,
                            "comment": evaluation.comment,
                        }
        return {
            "items": items,
            "alerts": copy.deepcopy(self._snapshot["alerts"]),
            "tickets": copy.deepcopy(self._snapshot["tickets"]),
            "knowledgeArticles": copy.deepcopy(self._snapshot["knowledge_articles"]),
        }

    def get_provider_view(self) -> dict[str, Any]:
        provider = copy.deepcopy(self._snapshot["provider"])
        store = self._state_store.database_store
        if store is None:
            return provider
        packages = self.list_packages()
        delivery = self.get_delivery_task("DLV-2026-04-25-0011")
        resource = self.get_resource("res-jbxx-ledger")
        provider["overview"][2]["value"] = str(len(delivery.get("backflow", {}).get("candidateFields", [])))
        provider["resources"][0]["status"] = resource.get("status", provider["resources"][0]["status"])
        provider["resources"][0]["updatedAt"] = resource.get("updatedAt", provider["resources"][0]["updatedAt"])
        provider["repository"] = {
            "packageCount": len(packages),
            "resourceCatalogCode": resource.get("repository", {}).get("catalogCode"),
            "deliveryReceiptCount": len(delivery.get("receipts", [])),
        }
        return provider

    def get_resource(self, resource_id: str) -> dict[str, Any]:
        store = self._state_store.database_store
        snapshot_miss = False
        try:
            resource = copy.deepcopy(self._resource_by_id(resource_id))
        except NotFoundError:
            if store is None:
                raise
            snapshot_miss = True
            resource = {}
        if store is None:
            return resource
        record = store.catalog_repo.get_entry(resource_id, tenant_id=_DEFAULT_TENANT_ID)
        if record is not None:
            return self._catalog_record_to_card_dict(record)
        if snapshot_miss:
            raise NotFoundError(resource_id)
        return resource

    def get_request(self, request_id: str) -> dict[str, Any]:
        request = copy.deepcopy(self._request_by_id(request_id))
        store = self._state_store.database_store
        if store is None:
            return request
        for record in store.application_repo.list_records(tenant_id=_DEFAULT_TENANT_ID):
            if record.application_code == request_id:
                request["status"] = record.status
                request["repository"] = {
                    "application_code": record.application_code,
                    "applicant_name": record.applicant_name,
                    "applicant_org": record.applicant_org,
                }
                break
        return request

    def get_approval(self, request_id: str) -> dict[str, Any]:
        approval = copy.deepcopy(self._approval_by_id(request_id))
        store = self._state_store.database_store
        if store is None:
            return approval
        case = next((item for item in store.approval_repo.list_cases(tenant_id=_DEFAULT_TENANT_ID) if item.application_code == request_id), None)
        if case is not None:
            approval["case"] = {
                "currentStatus": case.current_status,
                "currentStep": case.current_step,
            }
            approval["steps"] = [
                {
                    "stepNo": item.step_no,
                    "stepName": item.step_name,
                    "decisionMode": item.decision_mode,
                    "status": item.status,
                    "approverScope": copy.deepcopy(item.approver_scope_json),
                }
                for item in store.approval_repo.list_steps(request_id)
            ]
            approval["decisions"] = [
                {
                    "decision": item.decision,
                    "decisionReason": item.decision_reason,
                    "actorSnapshot": copy.deepcopy(item.actor_snapshot_json),
                    "evidence": copy.deepcopy(item.evidence_json),
                }
                for item in store.approval_repo.list_decisions(request_id)
            ]
        return approval

    def get_delivery_task(self, task_id: str) -> dict[str, Any]:
        task = copy.deepcopy(self._delivery_by_id(task_id))
        store = self._state_store.database_store
        if store is None:
            return task
        record = next((item for item in store.delivery_repo.list_tasks(tenant_id=_DEFAULT_TENANT_ID) if item.delivery_code == task_id), None)
        if record is not None:
            task["status"] = record.state
            task["repository"] = {
                "delivery_code": record.delivery_code,
                "application_code": record.application_code,
                "channel": record.channel,
            }
            task["receipts"] = [
                {
                    "receiptType": item.receipt_type,
                    "receiptNo": item.receipt_no,
                    "receiptStatus": item.receipt_status,
                    "payload": copy.deepcopy(item.payload_json),
                }
                for item in store.delivery_repo.list_receipts(task_id)
            ]
            if task["receipts"]:
                task["receiptStatus"] = task["receipts"][-1]["receiptStatus"]
                task["receiptNo"] = task["receipts"][-1]["receiptNo"]
        return task

    def get_dispute(self, dispute_id: str) -> dict[str, Any]:
        dispute = next((copy.deepcopy(item) for item in self._snapshot["disputes"] if item["id"] == dispute_id), None)
        if dispute is None:
            raise NotFoundError(dispute_id)
        store = self._state_store.database_store
        if store is None:
            return dispute
        record = store.objection_repo.get_case(dispute_id)
        if record is None:
            return dispute
        dispute["repository"] = {
            "objectionKind": record.objection_kind,
            "targetType": record.target_type,
            "status": record.status,
        }
        dispute["process"] = [
            {
                "nodeName": item.node_name,
                "actionType": item.action_type,
                "actionResult": item.action_result,
                "opinion": item.opinion,
            }
            for item in store.objection_repo.list_processes(dispute_id)
        ]
        evaluation = store.objection_repo.get_evaluation(dispute_id)
        if evaluation is not None:
            dispute["evaluation"] = {
                "solvedFlag": evaluation.solved_flag,
                "overallScore": evaluation.overall_score,
                "comment": evaluation.comment,
            }
        return dispute

    def replay_evidence_chain(self, dispute_id: str) -> dict[str, Any]:
        dispute = self.get_dispute(dispute_id)
        evidence = [
            {
                "time": step.get("time") or step.get("payload", {}).get("time") or "—",
                "label": step.get("label") or step.get("nodeName") or "证据",
                "detail": step.get("note") or step.get("opinion") or "—",
            }
            for step in dispute.get("timeline", [])
        ]
        audit_events = [
            item
            for item in self.list_audit_events()
            if item["target"] in {dispute_id, "REQ-2026-04-24-0007", "REQ-2026-04-25-0011"}
        ]
        return {
            "disputeId": dispute_id,
            "summary": dispute.get("aiSummary"),
            "evidenceChain": evidence,
            "auditEvents": audit_events,
            "tickets": [item for item in self._snapshot["tickets"] if item["id"] in {"TK-2026-04-25-014", "TK-2026-04-25-015"}],
            "knowledgeArticles": [item for item in self._snapshot["knowledge_articles"] if item["id"] in {"KB-REDUCE-BURDEN-02", "KB-TEMPLATE-BACKFLOW-01"}],
        }

    def ingest_delivery_receipt(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))
        task_id = str(payload["task_id"])

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            task = self._maybe_delivery(task_id)
            if task is not None:
                task["receiptStatus"] = str(payload["receipt_status"])
                task["receiptNo"] = payload.get("receipt", {}).get("receipt_no") or payload.get("receipt_no") or task.get("receiptNo")
                task["updatedAt"] = self._now_datetime()
                task.setdefault("history", []).append({"time": self._now_short_time(), "state": "回执已接收", "detail": f"交付回执状态：{payload['receipt_status']}。"})
            receipt = self._delivery_repo().append_receipt(
                {
                    "delivery_code": task_id,
                    "receipt_type": "exchange",
                    "receipt_no": payload.get("receipt", {}).get("receipt_no") or payload.get("receipt_no"),
                    "receipt_status": payload["receipt_status"],
                    "payload_json": payload.get("receipt") or {},
                }
            )
            if payload.get("attempt_id"):
                self._delivery_repo().add_execution_evidence(
                    {
                        "evidence_ref": audit_id,
                        "delivery_code": task_id,
                        "attempt_code": payload.get("attempt_id"),
                        "executor_kind": "exchange_receipt",
                        "evidence_kind": "delivery_receipt",
                        "result_status": payload["receipt_status"],
                        "payload_json": payload.get("receipt") or payload,
                    }
                )
            if isinstance(payload.get("metrics"), dict):
                self._delivery_repo().upsert_exchange_metric(payload["metrics"] | {"delivery_code": task_id, "status": payload["receipt_status"]})
            self._append_audit_feed("delivery.receipt.ingest", task_id, "ok", actor)
            return {"task_id": task_id, "receipt_status": receipt.receipt_status, "receipt_id": receipt.id, "audit_id": audit_id}

        return self._mutate("delivery.receipt.ingest", role, confirmed, payload, mutation)

    def query_exchange_statistics(self, **filters: Any) -> dict[str, Any]:
        metrics = [self._exchange_metric_record_to_dict(item) for item in self._delivery_repo().list_exchange_metrics(**filters, tenant_id=_DEFAULT_TENANT_ID)]
        return {"items": metrics, "summary": self._exchange_metric_summary(metrics)}

    def diagnose_exchange(self, *, task_id: Any = None, attempt_id: Any = None) -> dict[str, Any]:
        delivery_code = str(task_id) if task_id else None
        attempt_code = str(attempt_id) if attempt_id else None
        attempts = [self._delivery_attempt_record_to_dict(item) for item in self._delivery_repo().list_attempts(delivery_code=delivery_code, attempt_code=attempt_code)]
        evidence = [self._delivery_evidence_record_to_dict(item) for item in self._delivery_repo().list_execution_evidence(delivery_code=delivery_code, attempt_code=attempt_code, tenant_id=_DEFAULT_TENANT_ID)]
        metrics = [self._exchange_metric_record_to_dict(item) for item in self._delivery_repo().list_exchange_metrics(delivery_code=delivery_code, tenant_id=_DEFAULT_TENANT_ID)]
        return {"attempts": attempts, "evidence": evidence, "metrics": metrics, "diagnosis": {"state": "failed" if any(item["state"] in {"failed", "stopped"} for item in attempts) else "observable"}}

    def plan_delivery_exchange(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._record_delivery_attempt(payload, "delivery.exchange.plan", "planned", "plan")

    def start_delivery_exchange(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._record_delivery_attempt(payload, "delivery.exchange.start", "running", "exchange")

    def publish_delivery_exchange(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._record_delivery_attempt(payload, "delivery.exchange.publish", "published", "publish")

    def stop_delivery_exchange(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._record_delivery_attempt(payload, "delivery.exchange.stop", "stopped", "stop")

    def approve_application_grant(self, payload: dict[str, Any]) -> dict[str, Any]:
        decision = str(payload["decision"])
        if decision == "approve":
            return self.grant_delivery_access(str(payload["task_id"]), str(payload.get("role", self._ui_state["role"])), bool(payload.get("confirmed")))
        if decision in {"reject", "return_for_fix"}:
            task_id = str(payload["task_id"])
            role = str(payload.get("role", self._ui_state["role"]))
            confirmed = bool(payload.get("confirmed"))

            def mutation(audit_id: str, actor: str) -> dict[str, Any]:
                task = self._delivery_by_id(task_id)
                task["status"] = "warning"
                task["updatedAt"] = self._now_datetime()
                task["note"] = str(payload.get("reason", "授权申请未通过。"))
                task.setdefault("history", []).append({"time": self._now_short_time(), "state": "授权未通过", "detail": task["note"]})
                self._append_audit_feed("application.grant.approve", task_id, "warning", actor)
                return {"task_id": task_id, "decision": decision, "status": task["status"], "audit_id": audit_id}

            return self._mutate("application.grant.approve", role, confirmed, payload, mutation)
        raise BrainServiceError(f"unsupported grant decision: {decision}")

    def renew_application_grant(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))
        task_id = str(payload["task_id"])

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            task = self._delivery_by_id(task_id)
            task.setdefault("access", {})["renew_until"] = payload.get("renew_until")
            task["updatedAt"] = self._now_datetime()
            task.setdefault("history", []).append({"time": self._now_short_time(), "state": "授权已续期", "detail": str(payload.get("reason", "访问授权续期完成。"))})
            self._delivery_repo().add_execution_evidence({"evidence_ref": audit_id, "delivery_code": task_id, "executor_kind": "grant_policy", "evidence_kind": "grant_renewal", "result_status": "renewed", "payload_json": payload})
            self._append_audit_feed("application.grant.renew", task_id, "ok", actor)
            return {"task_id": task_id, "renew_until": payload.get("renew_until"), "audit_id": audit_id}

        return self._mutate("application.grant.renew", role, confirmed, payload, mutation)

    def submit_requirement_intent(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.create_request(str(payload.get("resource_id") or "res-jbxx-ledger"), str(payload.get("role", self._ui_state["role"])), bool(payload.get("confirmed")), str(payload.get("intent") or payload.get("title") or self._ui_state.get("discoveryQuery", "")), "require.intent.submit")

    def refine_requirement_intent(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))
        request_id = str(payload["request_id"])

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            request = self._request_by_id(request_id)
            request.setdefault("timeline", []).append({"label": "需求已细化", "time": self._now_datetime(), "note": str(payload.get("refine_note", "已补充需求意图与资源范围。"))})
            request["purpose"] = str(payload.get("refine_note") or request.get("purpose"))
            request["aiStatus"]["summary"] = "需求意图已细化，仍保持受控准入链路。"
            self._append_audit_feed("require.intent.refine", request_id, "ok", actor)
            return {"request_id": request_id, "status": request["status"], "audit_id": audit_id}

        return self._mutate("require.intent.refine", role, confirmed, payload, mutation)

    def review_requirement_intent(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.review_request(str(payload["request_id"]), str(payload["decision"]), str(payload.get("role", self._ui_state["role"])), bool(payload.get("confirmed")), "require.intent.review")

    def match_requirement_resource(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))
        request_id = str(payload["request_id"])

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            request = self._request_by_id(request_id)
            candidates = payload.get("candidate_resources") or ([payload["resource_id"]] if payload.get("resource_id") else [])
            request["matchedResources"] = safe_json(candidates)
            request.setdefault("timeline", []).append({"label": "资源匹配完成", "time": self._now_datetime(), "note": str(payload.get("match_note", "已生成候选资源匹配结果。"))})
            self._append_audit_feed("require.resource.match", request_id, "ok", actor)
            return {"request_id": request_id, "candidate_count": len(candidates), "audit_id": audit_id}

        return self._mutate("require.resource.match", role, confirmed, payload, mutation)

    def manage_delivery_subscription(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))
        action = str(payload["action"])
        if action not in {"create", "activate", "pause", "resume", "cancel"}:
            raise InvalidStateError(f"unsupported subscription action: {action}")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            task = self._delivery_by_id(str(payload["task_id"]))
            status = {"create": "active", "activate": "active", "pause": "paused", "resume": "active", "cancel": "cancelled"}[action]
            subscription = self._delivery_repo().upsert_subscription({"subscription_code": payload.get("subscription_id"), "delivery_code": task["id"], "resource_code": task.get("resourceId") or task.get("access", {}).get("resource_code"), "status": status, "schedule_ref": payload.get("schedule_ref") or {}, "policy_snapshot": payload.get("policy_snapshot") or {}, "legacy_status_snapshot": {"action": action, "task_status": task.get("status")}})
            task.setdefault("history", []).append({"time": self._now_short_time(), "state": "订阅策略已更新", "detail": f"订阅状态：{status}"})
            self._append_audit_feed("delivery.subscription.manage", task["id"], "ok", actor)
            return {"subscription_code": subscription.subscription_code, "status": subscription.status, "audit_id": audit_id}

        return self._mutate("delivery.subscription.manage", role, confirmed, payload, mutation)

    def _record_delivery_attempt(self, payload: dict[str, Any], skill_id: str, state: str, attempt_kind: str) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))
        task_id = str(payload["task_id"])

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            task = self._delivery_by_id(task_id)
            attempt = self._delivery_repo().upsert_attempt({"attempt_code": payload.get("attempt_id") or f"{task_id}:{attempt_kind}:{audit_id}", "delivery_code": task_id, "subscription_code": payload.get("subscription_id"), "attempt_kind": attempt_kind, "state": state, "executor_ref": payload.get("executor_ref"), "evidence_ref": audit_id, "payload_json": payload.get("plan") or payload})
            task["updatedAt"] = self._now_datetime()
            task.setdefault("history", []).append({"time": self._now_short_time(), "state": f"交换交付{state}", "detail": str(payload.get("reason") or payload.get("mode") or attempt_kind)})
            self._delivery_repo().add_execution_evidence({"evidence_ref": audit_id, "delivery_code": task_id, "attempt_code": attempt.attempt_code, "executor_kind": "builtin_exchange", "executor_ref": payload.get("executor_ref"), "evidence_kind": attempt_kind, "result_status": state, "payload_json": payload})
            self._delivery_repo().upsert_exchange_metric({"metric_scope": "delivery", "delivery_code": task_id, "resource_code": payload.get("resource_id") or task.get("resourceId"), "subscription_code": payload.get("subscription_id"), "status": state, "success_count": 1 if state in {"published", "running", "planned"} else 0, "failed_count": 1 if state == "stopped" else 0, "summary_json": {"skill_id": skill_id, "state": state}})
            self._append_audit_feed(skill_id, task_id, "ok", actor)
            return {"task_id": task_id, "attempt_code": attempt.attempt_code, "state": attempt.state, "audit_id": audit_id}

        return self._mutate(skill_id, role, confirmed, payload, mutation)

    def _delivery_repo(self) -> DeliveryRepository:
        store = self._state_store.database_store
        return store.delivery_repo if store is not None else DeliveryRepository()

    def get_zone(self, zone_id: str) -> dict[str, Any]:
        for item in self.list_zones():
            if item["id"] == zone_id:
                return copy.deepcopy(item)
        raise NotFoundError(zone_id)

    def get_package(self, package_id: str) -> dict[str, Any]:
        package = copy.deepcopy(self._package_by_id(package_id))
        store = self._state_store.database_store
        if store is None:
            return package
        for record in store.capability_package_repo.list_packages():
            if record.manifest_json.get("id") == package_id or record.package_slug == package.get("slug"):
                package["status"] = record.review_status
                package["repository"] = {
                    "packageSlug": record.package_slug,
                    "sourceOrg": record.source_org,
                }
                break
        policies = store.capability_package_repo.list_policies()
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

    def get_dashboard(self) -> dict[str, Any]:
        dashboard = copy.deepcopy(self._snapshot["dashboard"])
        provider = self.get_provider_view()
        packages = self.list_packages()
        requests = self.list_requests()
        audit_items = self.list_audit_events()
        dashboard["brainOutage"] = self._ui_state["brainOutage"]
        dashboard["mode"] = "snapshot" if self._ui_state["brainOutage"] else "live-readonly"
        service_report = self.query_service_report()
        dashboard["summary"]["alerts"] = str(sum(1 for item in requests if item["status"] in {"need-fix", "rejected"}) + service_report["summary"]["gatewayWarnings"])
        dashboard["summary"]["qps"] = str(service_report["summary"]["invokeCount"])
        dashboard["summary"]["agentsOnline"] = str(service_report["summary"]["gatewayCount"])
        dashboard["repository"] = {
            "requestCount": len(requests),
            "packageCount": len(packages),
            "auditEventCount": len(audit_items),
            "providerResourceCatalogCode": provider.get("repository", {}).get("resourceCatalogCode"),
            "gatewayCount": service_report["summary"]["gatewayCount"],
            "serviceInvokeCount": service_report["summary"]["invokeCount"],
            "serviceFailureCount": service_report["summary"]["failedCount"],
        }
        return dashboard

    def search_resources(self, query: str, page: int = 1) -> dict[str, Any]:
        query = query.strip()
        store = self._state_store.database_store
        if store is None:
            haystack = query.lower()
            resources = []
            for item in self._snapshot["discovery"]["resources"]:
                text = " ".join(
                    [
                        item["name"],
                        item["desc"],
                        item["provider"],
                        item["zone"],
                        " ".join(item.get("fields", [])),
                        " ".join(item.get("explain", [])),
                    ]
                ).lower()
                if not haystack or haystack in text:
                    resources.append(copy.deepcopy(item))
            for api_res in self._snapshot.get("api_resources", []):
                if api_res.get("lifecycle_status") in {"draft", "revoked"}:
                    continue
                summary = api_res.get("summary_json") or {}
                text = " ".join(
                    [
                        api_res.get("title", ""),
                        api_res.get("resource_code", ""),
                        api_res.get("owner_org_id", ""),
                        str(summary.get("domain", "")),
                        str(summary.get("desc", "")),
                    ]
                ).lower()
                if not haystack or haystack in text:
                    resources.append(
                        {
                            "id": api_res["resource_code"],
                            "name": api_res.get("title", api_res["resource_code"]),
                            "provider": api_res.get("owner_org_id", ""),
                            "zone": "API 资源",
                            "status": api_res.get("lifecycle_status", "active"),
                            "desc": str(summary.get("desc") or summary.get("domain") or api_res.get("title", "")),
                            "kind": "api",
                            "resource_kind": api_res.get("resource_kind"),
                        }
                    )
            # NL recall — append real-catalog candidates from the recall dictionary
            # when the query matches a dictionary title. Only fires when query is
            # non-empty (would otherwise add 25 thin cards to every page load).
            if haystack:
                seen_ids = {r["id"] for r in resources}
                recall = self._snapshot.get("discovery", {}).get("recallDictionary", {})
                for entry in recall.get("sample_titles", []):
                    title = entry.get("title", "")
                    if not title or haystack not in title.lower():
                        continue
                    cand_id = f"recall:{title}"
                    if cand_id in seen_ids:
                        continue
                    seen_ids.add(cand_id)
                    resources.append(
                        {
                            "id": cand_id,
                            "name": title,
                            "provider": entry.get("owner_org_id", "") or "—",
                            "zone": "真目录召回",
                            "status": entry.get("lifecycle_status", "active"),
                            "desc": f"NL 召回字典命中（来自 dsp_catalog 真数据，{entry.get('lifecycle_status','active')}）。",
                            "kind": "recall_dictionary",
                            "score": 60,
                        }
                    )
        else:
            if not query:
                resources = [copy.deepcopy(item) for item in self._snapshot["discovery"]["resources"]]
            else:
                records = store.catalog_repo.search_entries(query, tenant_id=_DEFAULT_TENANT_ID)
                resources = [self._catalog_record_to_card_dict(record) for record in records]
        page = max(page, 1)
        page_size = 20
        start = (page - 1) * page_size
        end = start + page_size
        return {
            "query": query,
            "page": page,
            "results": resources[start:end],
            "total": len(resources),
            "summary": copy.deepcopy(self._snapshot["discovery"]["aiCopilot"]),
        }

    def query_catalog_groups(self) -> dict[str, Any]:
        catalogs = copy.deepcopy(self._snapshot.get("provider", {}).get("catalogs", []))
        groups: dict[str, dict[str, Any]] = {}
        for catalog in catalogs:
            key = str(catalog.get("domain") or catalog.get("group") or "default")
            group = groups.setdefault(key, {"group_code": key, "title": key, "catalog_count": 0})
            group["catalog_count"] += 1
        return {"items": list(groups.values()), "total": len(groups)}

    def query_catalog_share_zones(self) -> dict[str, Any]:
        zones = []
        for zone in self._snapshot.get("zones", []):
            zones.append(
                {
                    "zone_id": zone.get("id"),
                    "title": zone.get("title") or zone.get("name"),
                    "status": zone.get("status"),
                    "trust": copy.deepcopy(zone.get("trust", [])),
                    "next_actions": copy.deepcopy(zone.get("nextActions", [])),
                }
            )
        return {"items": zones, "total": len(zones)}

    def query_catalog_models(self, *, model_code: Any = None) -> dict[str, Any]:
        store = self._state_store.database_store
        repo = store.catalog_repo if store is not None else CatalogRepository()
        models = [self._catalog_model_record_to_dict(item) for item in repo.list_models(tenant_id=_DEFAULT_TENANT_ID)]
        if model_code:
            models = [item for item in models if item["model_code"] == str(model_code)]
        return {"items": models, "total": len(models)}

    def query_catalog_model_fields(self, model_code: str) -> dict[str, Any]:
        store = self._state_store.database_store
        repo = store.catalog_repo if store is not None else CatalogRepository()
        fields = [self._catalog_model_field_record_to_dict(item) for item in repo.list_model_fields(model_code, tenant_id=_DEFAULT_TENANT_ID)]
        return {"items": fields, "total": len(fields)}

    def query_catalog_entries(self, *, query: Any = None, catalog_code: Any = None) -> dict[str, Any]:
        store = self._state_store.database_store
        repo = store.catalog_repo if store is not None else CatalogRepository()
        if query:
            records = repo.search_entries(str(query), tenant_id=_DEFAULT_TENANT_ID)
        else:
            records = repo.list_entries(tenant_id=_DEFAULT_TENANT_ID)
        entries = [self._catalog_entry_record_to_dict(item) for item in records]
        if catalog_code:
            entries = [item for item in entries if item["catalog_code"] == str(catalog_code)]
        return {"items": entries, "total": len(entries)}

    def browse_catalog_entries(
        self,
        *,
        page: Any = None,
        limit: Any = None,
        lifecycle: Any = None,
        kind: Any = None,
        owner_org_id: Any = None,
        query: Any = None,
    ) -> dict[str, Any]:
        """Paginated browse of catalog_entry. Defaults filter out retired/draft
        noise and api-group nodes so the WebUI surface stays customer-grade.

        Filters:
          - lifecycle: 'active' (default) | 'approved_pending_publish' | 'draft' | 'pending_review' | 'rejected' | 'all'
          - kind: 'real' (default; excludes catalog_code starting with 'api-group:') | 'api-group' | 'all'
        """
        page = max(int(page or 1), 1)
        limit = max(min(int(limit or 20), 100), 1)
        lifecycle = str(lifecycle or "active")
        kind = str(kind or "real")

        store = self._state_store.database_store
        repo = store.catalog_repo if store is not None else CatalogRepository()
        records = repo.search_entries(str(query), tenant_id=_DEFAULT_TENANT_ID) if query else repo.list_entries(tenant_id=_DEFAULT_TENANT_ID)

        if lifecycle != "all":
            records = [r for r in records if r.lifecycle_status == lifecycle]
        if kind == "real":
            records = [r for r in records if not r.catalog_code.startswith("api-group:")]
        elif kind == "api-group":
            records = [r for r in records if r.catalog_code.startswith("api-group:")]
        if owner_org_id:
            records = [r for r in records if r.owner_org_id == str(owner_org_id)]

        total = len(records)
        start = (page - 1) * limit
        end = start + limit
        items = [self._catalog_entry_record_to_dict(r) for r in records[start:end]]
        return {"items": items, "total": total, "page": page, "limit": limit}

    def query_resource_assets(self, *, resource_code: Any = None) -> dict[str, Any]:
        store = self._state_store.database_store
        if store is None:
            resources = copy.deepcopy(self._snapshot.get("api_resources", []))
            if resource_code:
                resources = [item for item in resources if item.get("resource_code") == resource_code]
        else:
            resources = [self._resource_asset_record_to_dict(item) for item in store.resource_api_repo.list_assets(tenant_id=_DEFAULT_TENANT_ID)]
            if resource_code:
                resources = [item for item in resources if item["resource_code"] == str(resource_code)]
        return {"items": resources, "total": len(resources)}

    def query_metadata_schema(self, *, resource_code: Any = None, binding_code: Any = None) -> dict[str, Any]:
        store = self._state_store.database_store
        if store is None:
            return {"items": [], "total": 0}
        items = [
            self._schema_snapshot_record_to_dict(item)
            for item in store.metadata_evidence_repo.list_schema_snapshots(
                resource_code=str(resource_code) if resource_code else None,
                binding_code=str(binding_code) if binding_code else None,
                tenant_id=_DEFAULT_TENANT_ID,
            )
        ]
        return {"items": items, "total": len(items)}

    def query_metadata_catalog_items(self, *, resource_code: Any = None, catalog_code: Any = None) -> dict[str, Any]:
        store = self._state_store.database_store
        if store is None:
            return {"items": [], "total": 0}
        items = [
            self._schema_mapping_record_to_dict(item)
            for item in store.metadata_evidence_repo.list_schema_mappings(
                resource_code=str(resource_code) if resource_code else None,
                catalog_code=str(catalog_code) if catalog_code else None,
                tenant_id=_DEFAULT_TENANT_ID,
            )
        ]
        return {"items": items, "total": len(items)}

    def query_metadata_gather_evidence(self, *, resource_code: Any = None, status: Any = None) -> dict[str, Any]:
        store = self._state_store.database_store
        if store is None:
            return {"items": [], "total": 0}
        items = [
            self._gather_evidence_record_to_dict(item)
            for item in store.metadata_evidence_repo.list_gather_evidence(
                resource_code=str(resource_code) if resource_code else None,
                status=str(status) if status else None,
                tenant_id=_DEFAULT_TENANT_ID,
            )
        ]
        return {"items": items, "total": len(items)}

    def query_metadata_lineage(self, *, resource_code: Any = None, relation_scope: Any = None) -> dict[str, Any]:
        store = self._state_store.database_store
        if store is None:
            return {"items": [], "total": 0}
        items = [
            self._lineage_record_to_dict(item)
            for item in store.metadata_evidence_repo.list_lineage_relations(
                resource_code=str(resource_code) if resource_code else None,
                relation_scope=str(relation_scope) if relation_scope else None,
                tenant_id=_DEFAULT_TENANT_ID,
            )
        ]
        return {"items": items, "total": len(items)}

    def query_catalog_quality(self, *, target_type: Any = None, target_ref: Any = None) -> dict[str, Any]:
        store = self._state_store.database_store
        if store is None:
            return {"items": [], "total": 0}
        items = [
            self._quality_record_to_dict(item)
            for item in store.metadata_evidence_repo.list_quality_evidence(
                target_type=str(target_type) if target_type else None,
                target_ref=str(target_ref) if target_ref else None,
                tenant_id=_DEFAULT_TENANT_ID,
            )
        ]
        return {"items": items, "total": len(items)}

    def query_catalog_statistics(self) -> dict[str, Any]:
        store = self._state_store.database_store
        if store is None:
            return {
                "summary": {
                    "catalogCount": len(self._snapshot.get("catalog_items", [])),
                    "resourceCount": len(self._snapshot.get("api_resources", [])),
                    "schemaMappingCount": 0,
                    "qualityEvidenceCount": 0,
                    "source_ref": "seed_snapshot",
                    "generated_at": self._now_datetime(),
                    "projection_only": True,
                }
            }
        catalog_count = len(store.catalog_repo.list_entries(tenant_id=_DEFAULT_TENANT_ID))
        resource_count = len(store.resource_api_repo.list_assets(tenant_id=_DEFAULT_TENANT_ID))
        schema_mapping_count = len(store.metadata_evidence_repo.list_schema_mappings(tenant_id=_DEFAULT_TENANT_ID))
        quality_count = len(store.metadata_evidence_repo.list_quality_evidence(tenant_id=_DEFAULT_TENANT_ID))
        return {
            "summary": {
                "catalogCount": catalog_count,
                "resourceCount": resource_count,
                "schemaMappingCount": schema_mapping_count,
                "qualityEvidenceCount": quality_count,
                "source_ref": "canonical_projection",
                "generated_at": self._now_datetime(),
                "projection_only": True,
            }
        }

    def query_service_invocations(
        self,
        resource_code: Any = None,
        capability_id: Any = None,
        metric_scope: Any = None,
    ) -> dict[str, Any]:
        store = self._state_store.database_store
        if store is None:
            metrics = copy.deepcopy(self._snapshot.get("service_invocation_metrics", []))
            if resource_code:
                metrics = [item for item in metrics if item.get("resource_code") == resource_code]
            if capability_id:
                metrics = [item for item in metrics if item.get("capability_id") == capability_id]
            if metric_scope:
                metrics = [item for item in metrics if item.get("metric_scope") == metric_scope]
        else:
            metrics = [
                self._metric_record_to_dict(item)
                for item in store.service_invocation_repo.list_metrics(
                    resource_code=str(resource_code) if resource_code else None,
                    capability_id=str(capability_id) if capability_id else None,
                    metric_scope=str(metric_scope) if metric_scope else None,
                )
            ]
        return {"items": metrics, "summary": self._metric_summary(metrics)}

    def query_service_report(self) -> dict[str, Any]:
        store = self._state_store.database_store
        if store is None:
            gateways = copy.deepcopy(self._snapshot.get("gateway_runtime_statuses", []))
            metrics = copy.deepcopy(self._snapshot.get("service_invocation_metrics", []))
        else:
            gateways = [self._gateway_record_to_dict(item) for item in store.gateway_runtime_repo.list_statuses()]
            metrics = [self._metric_record_to_dict(item) for item in store.service_invocation_repo.list_metrics()]
        offline = sum(1 for item in gateways if item.get("status") != "online")
        metric_summary = self._metric_summary(metrics)
        return {
            "gateways": gateways,
            "metrics": metrics,
            "summary": {
                "gatewayCount": len(gateways),
                "gatewayWarnings": offline,
                "invokeCount": metric_summary["invokeCount"],
                "failedCount": metric_summary["failedCount"],
                "errorCount": metric_summary["errorCount"],
            },
        }

    def ingest_gateway_heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))
        status = str(payload.get("status", "online"))
        if status not in {"online", "warning", "offline"}:
            raise BrainServiceError(f"unsupported gateway status: {status}")
        gateway_payload = {
            "gateway_instance_id": str(payload["gateway_instance_id"]),
            "gateway_address_ref": payload.get("gateway_address_ref"),
            "runtime_profile": payload.get("runtime_profile"),
            "status": status,
            "last_reported_at": payload.get("last_reported_at") or datetime.now().isoformat(),
            "source_ref": payload.get("source_ref") or "gateway-heartbeat",
            "summary_json": copy.deepcopy(payload.get("summary_json", {})),
        }

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            store = self._state_store.database_store
            if store is None:
                statuses = self._snapshot.setdefault("gateway_runtime_statuses", [])
                current = next((item for item in statuses if item["gateway_instance_id"] == gateway_payload["gateway_instance_id"]), None)
                if current is None:
                    current = copy.deepcopy(gateway_payload)
                    statuses.append(current)
                else:
                    current.update(copy.deepcopy(gateway_payload))
                result = copy.deepcopy(current)
            else:
                result = self._gateway_record_to_dict(store.gateway_runtime_repo.upsert_heartbeat(gateway_payload))
            self._append_audit_feed("ops.gateway.heartbeat", gateway_payload["gateway_instance_id"], "ok", actor)
            return result | {"audit_id": audit_id}

        return self._mutate("ops.gateway.heartbeat.ingest", role, confirmed, gateway_payload, mutation)

    def upsert_catalog_model(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            store = self._state_store.database_store
            repo = store.catalog_repo if store is not None else CatalogRepository()
            model = repo.upsert_model(payload)
            for field in payload.get("fields") or []:
                repo.upsert_model_field({**field, "model_code": model.model_code})
            self._append_audit_feed("catalog.model.upsert", model.model_code, "ok", actor)
            return {"model_code": model.model_code, "status": model.status, "audit_id": audit_id}

        return self._mutate("catalog.model.upsert", role, confirmed, payload, mutation)

    def upsert_catalog_schema_mapping(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            store = self._state_store.database_store
            repo = store.metadata_evidence_repo if store is not None else MetadataEvidenceRepository()
            mapping = repo.upsert_schema_mapping({**payload, "confirmed_by": payload.get("confirmed_by") or actor})
            self._append_audit_feed("catalog.schema.mapping.upsert", mapping.mapping_code, "ok", actor)
            return {"mapping_code": mapping.mapping_code, "status": mapping.status, "audit_id": audit_id}

        return self._mutate("catalog.schema.mapping.upsert", role, confirmed, payload, mutation)

    def upsert_metadata_schema_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            store = self._state_store.database_store
            repo = store.metadata_evidence_repo if store is not None else MetadataEvidenceRepository()
            snapshot = repo.upsert_schema_snapshot(payload)
            self._append_audit_feed("metadata.schema.snapshot.upsert", snapshot.snapshot_ref, "ok", actor)
            return {"snapshot_ref": snapshot.snapshot_ref, "schema_hash": snapshot.schema_hash, "audit_id": audit_id}

        return self._mutate("metadata.schema.snapshot.upsert", role, confirmed, payload, mutation)

    def upsert_metadata_gather_evidence(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            store = self._state_store.database_store
            repo = store.metadata_evidence_repo if store is not None else MetadataEvidenceRepository()
            evidence = repo.upsert_gather_evidence(payload)
            self._append_audit_feed("metadata.gather.evidence.upsert", evidence.gather_task_ref, "ok", actor)
            return {"gather_task_ref": evidence.gather_task_ref, "status": evidence.status, "audit_id": audit_id}

        return self._mutate("metadata.gather.evidence.upsert", role, confirmed, payload, mutation)

    def upsert_metadata_lineage(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            store = self._state_store.database_store
            repo = store.metadata_evidence_repo if store is not None else MetadataEvidenceRepository()
            relation = repo.upsert_lineage_relation(payload)
            self._append_audit_feed("metadata.lineage.upsert", relation.relation_ref, "ok", actor)
            return {"relation_ref": relation.relation_ref, "relation_type": relation.relation_type, "audit_id": audit_id}

        return self._mutate("metadata.lineage.upsert", role, confirmed, payload, mutation)

    def upsert_catalog_quality_evidence(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            store = self._state_store.database_store
            repo = store.metadata_evidence_repo if store is not None else MetadataEvidenceRepository()
            evidence = repo.upsert_quality_evidence(payload)
            self._append_audit_feed("ops.catalog.quality.upsert", evidence.quality_ref, "ok", actor)
            return {"quality_ref": evidence.quality_ref, "quality_status": evidence.quality_status, "audit_id": audit_id}

        return self._mutate("ops.catalog.quality.upsert", role, confirmed, payload, mutation)

    def create_catalog_entry_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))
        catalog_code = str(payload["catalog_code"])

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            store = self._state_store.database_store
            catalog_payload = {
                "id": catalog_code,
                "name": str(payload.get("title", catalog_code)),
                "status": "draft",
                "provider": payload.get("owner_org_id", ""),
                "region_code": payload.get("region_code"),
                "source_ref": payload.get("source_ref"),
                "legacy_object_ref": payload.get("legacy_object_ref") or catalog_code,
                "summary_json": self._safe_json(payload.get("summary_json") or {}),
            }
            repo = store.catalog_repo if store is not None else CatalogRepository()
            repo.upsert_from_resource(catalog_payload, tenant_id=_DEFAULT_TENANT_ID)
            for item in payload.get("items") or []:
                repo.upsert_item({**item, "catalog_code": catalog_code}, tenant_id=_DEFAULT_TENANT_ID)
            self._append_audit_feed("catalog.entry.create_draft", catalog_code, "ok", actor)
            return {"catalog_code": catalog_code, "lifecycle_status": "draft", "audit_id": audit_id}

        return self._mutate("catalog.entry.create_draft", role, confirmed, payload, mutation)

    def submit_catalog_entry_review(self, catalog_code: str, role: str, confirmed: bool) -> dict[str, Any]:
        return self.transition_catalog_entry(catalog_code, "pending_review", "catalog.entry.submit_review", role, confirmed)

    def review_catalog_entry(self, catalog_code: str, decision: str, role: str, confirmed: bool) -> dict[str, Any]:
        if decision == "approve":
            return self.transition_catalog_entry(catalog_code, "approved_pending_publish", "catalog.entry.review", role, confirmed)
        if decision == "return_for_fix":
            return self.transition_catalog_entry(catalog_code, "draft", "catalog.entry.review", role, confirmed)
        if decision == "reject":
            return self.transition_catalog_entry(catalog_code, "rejected", "catalog.entry.review", role, confirmed)
        raise BrainServiceError(f"unsupported catalog entry review decision: {decision}")

    def transition_catalog_entry(self, catalog_code: str, status: str, skill_id: str, role: str, confirmed: bool) -> dict[str, Any]:
        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            store = self._state_store.database_store
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
            self._append_audit_feed(skill_id, catalog_code, "ok", actor)
            return {"catalog_code": catalog_code, "lifecycle_status": status, "audit_id": audit_id}

        return self._mutate(skill_id, role, confirmed, {"catalog_code": catalog_code, "status": status}, mutation)

    def update_catalog_entry(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))
        catalog_code = str(payload["catalog_code"])

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            store = self._state_store.database_store
            repo = store.catalog_repo if store is not None else CatalogRepository()
            existing = repo.get_entry(catalog_code, tenant_id=_DEFAULT_TENANT_ID)
            if existing is None:
                raise NotFoundError(catalog_code)
            repo.upsert_from_resource(
                {
                    **copy.deepcopy(existing.summary_json),
                    **self._safe_json(payload.get("summary_json") or {}),
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
            self._append_audit_feed("catalog.entry.update", catalog_code, "ok", actor)
            return {"catalog_code": catalog_code, "lifecycle_status": existing.lifecycle_status, "audit_id": audit_id}

        return self._mutate("catalog.entry.update", role, confirmed, payload, mutation)

    def bind_catalog_resource(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            store = self._state_store.database_store
            repo = store.metadata_evidence_repo if store is not None else MetadataEvidenceRepository()
            mapping = repo.upsert_schema_mapping({**payload, "confirmed_by": payload.get("confirmed_by") or actor})
            self._append_audit_feed("catalog.resource.bind", mapping.mapping_code, "ok", actor)
            return {"mapping_code": mapping.mapping_code, "status": mapping.status, "audit_id": audit_id}

        return self._mutate("catalog.resource.bind", role, confirmed, payload, mutation)

    def register_api_resource(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))
        resource = self._api_payload(payload, default_status="draft")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            result = self._upsert_api_resource(resource)
            binding = payload.get("channel_binding")
            if isinstance(binding, dict):
                self._upsert_api_binding({**binding, "resource_code": resource["resource_code"]})
            self._append_audit_feed("resource.api.register", resource["resource_code"], "ok", actor)
            return result | {"audit_id": audit_id}

        return self._mutate("resource.api.register", role, confirmed, resource, mutation)

    def change_api_resource(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))
        resource = self._api_payload(payload, default_status="draft")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            existing = self._find_api_resource(resource["resource_code"])
            if existing is None:
                raise NotFoundError(resource["resource_code"])
            result = self._upsert_api_resource({**existing, **resource})
            binding = payload.get("channel_binding")
            if isinstance(binding, dict):
                self._upsert_api_binding({**binding, "resource_code": resource["resource_code"]})
            self._append_audit_feed("resource.api.change", resource["resource_code"], "ok", actor)
            return result | {"audit_id": audit_id}

        return self._mutate("resource.api.change", role, confirmed, resource, mutation)

    def submit_api_resource_review(self, resource_code: str, role: str, confirmed: bool, skill_id: str = "resource.api.submit_review") -> dict[str, Any]:
        return self.transition_api_resource(resource_code, "pending_review", skill_id, role, confirmed)

    def review_api_resource(self, resource_code: str, decision: str, role: str, confirmed: bool, skill_id: str = "resource.api.review") -> dict[str, Any]:
        if decision == "approve":
            return self.transition_api_resource(resource_code, "approved_pending_publish", skill_id, role, confirmed)
        if decision == "return_for_fix":
            return self.transition_api_resource(resource_code, "draft", skill_id, role, confirmed)
        raise BrainServiceError(f"unsupported api resource review decision: {decision}")

    def transition_api_resource(self, resource_code: str, status: str, skill_id: str, role: str, confirmed: bool) -> dict[str, Any]:
        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            store = self._state_store.database_store
            if store is None:
                resource = self._find_api_resource(resource_code)
                if resource is None:
                    raise NotFoundError(resource_code)
                resource["lifecycle_status"] = status
                resource["updated_at"] = self._now_datetime()
                result = self._upsert_api_resource(resource)
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
                result = self._resource_asset_record_to_dict(record)
            self._append_audit_feed(skill_id, resource_code, "ok", actor)
            return result | {"audit_id": audit_id}

        return self._mutate(skill_id, role, confirmed, {"resource_code": resource_code, "status": status}, mutation)

    def test_api_resource(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
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
            "evidence_json": self._safe_json(payload.get("evidence_json") or {}),
            "legacy_object_ref": payload.get("legacy_object_ref"),
        }

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            store = self._state_store.database_store
            if store is None:
                resource = self._find_api_resource(resource_code)
                if resource is None:
                    raise NotFoundError(resource_code)
                resource["lifecycle_status"] = next_status
                resource["updated_at"] = self._now_datetime()
                result = self._upsert_api_resource(resource)
                tests = self._snapshot.setdefault("api_resource_tests", [])
                test_record = test_payload | {"test_ref": audit_id, "tested_by": actor, "tested_at": self._now_datetime()}
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
                result = self._resource_asset_record_to_dict(record)
                test_record = self._api_test_projection_record_to_dict(projection)
            self._append_audit_feed("resource.api.test", resource_code, "ok", actor)
            return result | {"audit_id": audit_id, "test_projection": test_record}

        return self._mutate("resource.api.test", role, confirmed, test_payload, mutation)

    def update_api_resource_policy(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))
        resource_code = str(payload["resource_code"])
        binding_code = str(payload["binding_code"])
        policy_payload = self._safe_json(payload.get("gateway_policy_json", {}))

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            if self._find_api_resource(resource_code) is None:
                raise NotFoundError(resource_code)
            binding = self._find_api_binding(binding_code)
            if binding is None or binding.get("resource_code") != resource_code:
                raise NotFoundError(binding_code)
            binding["gateway_policy_json"] = policy_payload
            result = self._upsert_api_binding(binding)
            self._append_audit_feed("resource.api.policy.update", resource_code, "ok", actor)
            return result | {"audit_id": audit_id}

        return self._mutate("resource.api.policy.update", role, confirmed, {"resource_code": resource_code, "binding_code": binding_code}, mutation)

    def anchor_gateway_log(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))
        gateway_log_ref = str(payload["gateway_log_ref"])
        evidence = self._safe_json(payload.get("evidence_json", {}))
        anchor_payload = {
            "gateway_log_ref": gateway_log_ref,
            "resource_code": payload.get("resource_code"),
            "source_ref": payload.get("source_ref") or gateway_log_ref,
            "evidence_json": evidence,
        }

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            store = self._state_store.database_store
            if store is not None:
                store.legacy_mapping_repo.upsert_mapping(
                    {
                        "source_ref": anchor_payload["source_ref"],
                        "legacy_object_ref": gateway_log_ref,
                        "canonical_type": "anchor_outbox",
                        "canonical_ref": audit_id,
                        "evidence_json": {"resource_code": anchor_payload.get("resource_code")},
                    }
                )
            self._append_audit_feed("ops.gateway.log.anchor", gateway_log_ref, "ok", actor)
            return anchor_payload | {"anchor_outbox_ref": audit_id, "audit_id": audit_id}

        return self._mutate("ops.gateway.log.anchor", role, confirmed, anchor_payload, mutation)

    def _api_payload(self, payload: dict[str, Any], *, default_status: str) -> dict[str, Any]:
        resource_code = str(payload["resource_code"])
        return {
            "resource_code": resource_code,
            "resource_kind": "api",
            "title": str(payload.get("title", resource_code)),
            "lifecycle_status": str(payload.get("lifecycle_status", default_status)),
            "owner_org_id": payload.get("owner_org_id"),
            "owner_org_snapshot_json": self._safe_json(payload.get("owner_org_snapshot_json") or {}),
            "region_code": payload.get("region_code"),
            "catalog_code": payload.get("catalog_code"),
            "access_policy_json": self._safe_json(payload.get("access_policy_json") or {}),
            "qos_policy_json": self._safe_json(payload.get("qos_policy_json") or {}),
            "source_ref": payload.get("source_ref"),
            "summary_json": self._safe_json(payload.get("summary_json") or {"title": payload.get("title", resource_code)}),
        }

    def _upsert_api_resource(self, resource: dict[str, Any]) -> dict[str, Any]:
        store = self._state_store.database_store
        if store is None:
            resources = self._snapshot.setdefault("api_resources", [])
            current = next((item for item in resources if item["resource_code"] == resource["resource_code"]), None)
            if current is None:
                current = copy.deepcopy(resource)
                current.setdefault("channel_bindings", [])
                resources.append(current)
            else:
                bindings = current.get("channel_bindings", [])
                current.update(copy.deepcopy(resource))
                current.setdefault("channel_bindings", bindings)
            return copy.deepcopy(current)
        return self._resource_asset_record_to_dict(store.resource_api_repo.upsert_asset(resource))

    def _upsert_api_binding(self, binding: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "binding_code": str(binding["binding_code"]),
            "resource_code": str(binding["resource_code"]),
            "channel_kind": str(binding.get("channel_kind", "api_gateway")),
            "route_ref": binding.get("route_ref"),
            "endpoint_ref": self._safe_json(binding.get("endpoint_ref", {})),
            "schema_ref": self._safe_json(binding.get("schema_ref", {})),
            "auth_ref": binding.get("auth_ref"),
            "request_schema_json": self._safe_json(binding.get("request_schema_json", {})),
            "response_schema_json": self._safe_json(binding.get("response_schema_json", {})),
            "gateway_policy_json": self._safe_json(binding.get("gateway_policy_json", {})),
            "lifecycle_status": str(binding.get("lifecycle_status", "draft")),
            "source_ref": binding.get("source_ref"),
        }
        store = self._state_store.database_store
        if store is None:
            resources = self._snapshot.setdefault("api_resources", [])
            resource = next((item for item in resources if item["resource_code"] == payload["resource_code"]), None)
            if resource is None:
                raise NotFoundError(payload["resource_code"])
            bindings = resource.setdefault("channel_bindings", [])
            current = next((item for item in bindings if item["binding_code"] == payload["binding_code"]), None)
            if current is None:
                current = copy.deepcopy(payload)
                bindings.append(current)
            else:
                current.update(copy.deepcopy(payload))
            return copy.deepcopy(current)
        return self._binding_record_to_dict(store.resource_api_repo.upsert_binding(payload))

    def _find_api_resource(self, resource_code: str) -> dict[str, Any] | None:
        store = self._state_store.database_store
        if store is None:
            item = next((item for item in self._snapshot.get("api_resources", []) if item["resource_code"] == resource_code), None)
            return copy.deepcopy(item) if item is not None else None
        record = store.resource_api_repo.get_asset(resource_code)
        return self._resource_asset_record_to_dict(record) if record is not None else None

    def _find_api_binding(self, binding_code: str) -> dict[str, Any] | None:
        store = self._state_store.database_store
        if store is None:
            for resource in self._snapshot.get("api_resources", []):
                binding = next((item for item in resource.get("channel_bindings", []) if item["binding_code"] == binding_code), None)
                if binding is not None:
                    return copy.deepcopy(binding)
            return None
        record = store.resource_api_repo.get_binding(binding_code)
        return self._binding_record_to_dict(record) if record is not None else None

    def _metric_summary(self, metrics: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "invokeCount": sum(int(item.get("invoke_count", 0)) for item in metrics),
            "successCount": sum(int(item.get("success_count", 0)) for item in metrics),
            "failedCount": sum(int(item.get("failed_count", item.get("failure_count", 0))) for item in metrics),
            "errorCount": sum(int(item.get("error_count", 0)) for item in metrics),
        }

    def _exchange_metric_summary(self, metrics: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "exchangeCount": sum(int(item.get("exchange_count", 0)) for item in metrics),
            "successCount": sum(int(item.get("success_count", 0)) for item in metrics),
            "failedCount": sum(int(item.get("failed_count", 0)) for item in metrics),
            "recordCount": sum(int(item.get("record_count", 0)) for item in metrics),
        }

    def _delivery_attempt_record_to_dict(self, record: Any) -> dict[str, Any]:
        return {
            "attempt_code": record.attempt_code,
            "delivery_code": record.delivery_code,
            "subscription_code": record.subscription_code,
            "attempt_kind": record.attempt_kind,
            "state": record.state,
            "executor_ref": record.executor_ref,
            "evidence_ref": record.evidence_ref,
            "payload_json": copy.deepcopy(record.payload_json),
        }

    def _delivery_evidence_record_to_dict(self, record: Any) -> dict[str, Any]:
        return {
            "evidence_ref": record.evidence_ref,
            "delivery_code": record.delivery_code,
            "attempt_code": record.attempt_code,
            "executor_kind": record.executor_kind,
            "executor_ref": record.executor_ref,
            "evidence_kind": record.evidence_kind,
            "result_status": record.result_status,
            "sanitized_payload_json": copy.deepcopy(record.sanitized_payload_json),
        }

    def _exchange_metric_record_to_dict(self, record: Any) -> dict[str, Any]:
        return {
            "metric_scope": record.metric_scope,
            "resource_code": record.resource_code,
            "delivery_code": record.delivery_code,
            "subscription_code": record.subscription_code,
            "provider_org_id": record.provider_org_id,
            "consumer_org_id": record.consumer_org_id,
            "bucket_granularity": record.bucket_granularity,
            "time_bucket": record.time_bucket,
            "exchange_count": record.exchange_count,
            "success_count": record.success_count,
            "failed_count": record.failed_count,
            "record_count": record.record_count,
            "file_count": record.file_count,
            "table_count": record.table_count,
            "last_error_code": record.last_error_code,
            "summary_json": copy.deepcopy(record.summary_json),
        }

    def _safe_json(self, value: dict[str, Any]) -> dict[str, Any]:
        return safe_json(value)

    def _decode_iaf_claims(self, iaf_claims: Any) -> dict[str, Any]:
        if isinstance(iaf_claims, dict):
            return self._safe_json(iaf_claims)
        token = str(iaf_claims or "")
        if not token:
            raise InvalidTokenError("missing token claims")
        if token.count(".") != 2:
            raise InvalidTokenError("invalid jwt format")
        payload_part = token.split(".")[1]
        payload_part += "=" * ((4 - len(payload_part) % 4) % 4)
        try:
            raw = base64.urlsafe_b64decode(payload_part.encode("utf-8")).decode("utf-8")
            payload = json.loads(raw)
        except Exception as exc:
            raise InvalidTokenError("invalid jwt payload") from exc
        if not isinstance(payload, dict):
            raise InvalidTokenError("invalid jwt claims type")
        return self._safe_json(payload)

    def _validate_iaf_claims(self, claims: dict[str, Any], *, expected_state: Any = None, expected_nonce: Any = None) -> None:
        now_ts = int(datetime.now(UTC).timestamp())
        exp = int(claims.get("exp") or 0)
        if exp <= now_ts:
            raise InvalidTokenError("token expired")
        expected_issuer = _expected_iaf_issuer()
        if expected_issuer and str(claims.get("iss") or "") != expected_issuer:
            raise InvalidTokenError("issuer mismatch")

        audience = claims.get("aud")
        if isinstance(audience, str):
            audience_set = {audience}
        elif isinstance(audience, list):
            audience_set = {str(item) for item in audience}
        else:
            audience_set = set()
        expected_audience = _expected_iaf_audience()
        client_id = str(claims.get("client_id") or claims.get("azp") or "")
        if expected_audience and expected_audience not in audience_set and client_id != expected_audience:
            raise InvalidTokenError("audience mismatch")

        if expected_state is not None and str(claims.get("state") or "") != str(expected_state):
            raise InvalidTokenError("state mismatch")
        if expected_nonce is not None and str(claims.get("nonce") or "") != str(expected_nonce):
            raise InvalidTokenError("nonce mismatch")

    def _build_actor_projection_from_claims(
        self,
        *,
        claims: Any,
        expected_state: Any = None,
        expected_nonce: Any = None,
        tenant_id: str,
        org_code: Any = None,
        fallback_roles: list[Any] | tuple[Any, ...] | None = None,
        display_name: Any = None,
    ) -> dict[str, Any]:
        claim_payload = self._decode_iaf_claims(claims)
        self._validate_iaf_claims(claim_payload, expected_state=expected_state, expected_nonce=expected_nonce)

        subject = str(claim_payload.get("sub") or "")
        if not subject:
            raise InvalidTokenError("missing sub")

        resource_roles = claim_payload.get("resource_access") or {}
        service_roles = resource_roles.get(_expected_iaf_audience(), {}) if isinstance(resource_roles, dict) else {}
        iam_roles = [str(item) for item in (service_roles.get("roles") if isinstance(service_roles, dict) else []) or []]
        realm_roles = [str(item) for item in ((claim_payload.get("realm_access") or {}).get("roles") or [])]
        merged_roles = sorted({*iam_roles, *realm_roles, *[str(item) for item in (fallback_roles or [])]})

        return {
            "tenant_id": tenant_id,
            "external_actor_id": subject,
            "display_name": str(display_name or claim_payload.get("preferred_username") or subject),
            "org_code": org_code,
            "role_codes": merged_roles,
            "status": "active",
            "source_ref": "iaf:claims",
            "profile_json": {
                "username": claim_payload.get("preferred_username"),
                "project_id": claim_payload.get("project_id"),
                "project": claim_payload.get("project"),
                "iam_role_codes": iam_roles,
                "realm_roles": realm_roles,
                "account_admin": "ACCOUNT_ADMIN" in realm_roles,
                "email": claim_payload.get("email"),
                "phone": claim_payload.get("phone"),
            },
            "iaf_claims": claim_payload,
        }

    def _actor_snapshot_from_projection(self, item: Any, *, claims: dict[str, Any]) -> dict[str, Any]:
        profile = item.profile_json if isinstance(item.profile_json, dict) else {}
        role_codes = [str(role) for role in item.role_codes_json or []]
        return {
            "subject": item.external_actor_id,
            "actor": f"user:iaf:{item.external_actor_id}",
            "tenant_id": item.tenant_id,
            "display_name": item.display_name,
            "org_code": item.org_code,
            "status": item.status,
            "role_codes": role_codes,
            "iam_role_codes": [str(role) for role in profile.get("iam_role_codes") or []],
            "account_flags": {"account_admin": bool(profile.get("account_admin"))},
            "issuer": claims.get("iss"),
            "audience": claims.get("aud"),
            "project_id": claims.get("project_id") or profile.get("project_id"),
            "project": claims.get("project") or profile.get("project"),
            "issued_at": datetime.now(UTC).isoformat(),
        }

    def _catalog_model_record_to_dict(self, record: Any) -> dict[str, Any]:
        return {
            "model_code": record.model_code,
            "title": record.title,
            "status": record.status,
            "owner_org_id": record.owner_org_id,
            "model_schema_json": copy.deepcopy(record.model_schema_json),
            "source_ref": record.source_ref,
        }

    def _catalog_model_field_record_to_dict(self, record: Any) -> dict[str, Any]:
        return {
            "model_code": record.model_code,
            "field_code": record.field_code,
            "title": record.title,
            "data_type": record.data_type,
            "sensitive_level": record.sensitive_level,
            "field_policy_json": copy.deepcopy(record.field_policy_json),
            "display_order": record.display_order,
            "source_ref": record.source_ref,
        }

    def _catalog_entry_record_to_dict(self, record: Any) -> dict[str, Any]:
        return {
            "catalog_code": record.catalog_code,
            "title": record.title,
            "lifecycle_status": record.lifecycle_status,
            "owner_org_id": record.owner_org_id,
            "region_code": record.region_code,
            "summary_json": _mask(copy.deepcopy(record.summary_json)),
        }

    def _catalog_record_to_card_dict(self, record: Any) -> dict[str, Any]:
        summary = _mask(copy.deepcopy(record.summary_json or {}))
        return {
            "id": record.catalog_code,
            "name": record.title,
            "status": record.lifecycle_status,
            "provider": record.owner_org_id or summary.get("provider", "—"),
            "zone": summary.get("zone", "真目录召回"),
            "updatedAt": str(summary.get("updatedAt") or summary.get("updated_at") or record.updated_at.date().isoformat()),
            "coverage": summary.get("coverage", "真目录"),
            "score": int(summary.get("score", 70)),
            "desc": str(summary.get("desc") or summary.get("summary") or record.title),
            "fields": list(summary.get("fields", [])),
            "explain": list(summary.get("explain", ["已匹配共享目录登记信息", f"目录状态：{record.lifecycle_status}"])),
            "nextHints": list(summary.get("nextHints", ["查看目录详情"])),
            "kind": summary.get("kind", "catalog_entry"),
            "repository": {
                "catalogCode": record.catalog_code,
                "lifecycleStatus": record.lifecycle_status,
                "ownerOrgId": record.owner_org_id,
            },
        }

    def _schema_snapshot_record_to_dict(self, record: Any) -> dict[str, Any]:
        return {
            "snapshot_ref": record.snapshot_ref,
            "resource_code": record.resource_code,
            "binding_code": record.binding_code,
            "schema_json": copy.deepcopy(record.schema_json),
            "source_ref": record.source_ref,
            "schema_hash": record.schema_hash,
            "captured_at": record.captured_at.isoformat(),
        }

    def _schema_mapping_record_to_dict(self, record: Any) -> dict[str, Any]:
        return {
            "mapping_code": record.mapping_code,
            "catalog_code": record.catalog_code,
            "catalog_item_code": record.catalog_item_code,
            "resource_code": record.resource_code,
            "binding_code": record.binding_code,
            "source_schema_ref": copy.deepcopy(record.source_schema_ref),
            "mapping_rule_json": copy.deepcopy(record.mapping_rule_json),
            "confidence_level": record.confidence_level,
            "evidence_ref": record.evidence_ref,
            "source_ref": record.evidence_ref,
            "status": record.status,
            "confirmed_by": record.confirmed_by,
            "confirmed_at": record.confirmed_at.isoformat() if record.confirmed_at else None,
            "generated_at": record.updated_at.isoformat(),
        }

    def _gather_evidence_record_to_dict(self, record: Any) -> dict[str, Any]:
        return {
            "gather_task_ref": record.gather_task_ref,
            "resource_code": record.resource_code,
            "source_system_ref": record.source_system_ref,
            "source_ref": record.source_system_ref,
            "schema_snapshot_ref": record.schema_snapshot_ref,
            "status": record.status,
            "error_summary": record.error_summary,
            "evidence_json": copy.deepcopy(record.evidence_json),
            "started_at": record.started_at,
            "finished_at": record.finished_at,
            "generated_at": record.generated_at.isoformat(),
            "projection_only": True,
        }

    def _lineage_record_to_dict(self, record: Any) -> dict[str, Any]:
        return {
            "relation_ref": record.relation_ref,
            "relation_scope": record.relation_scope,
            "source_resource_code": record.source_resource_code,
            "source_schema_ref": record.source_schema_ref,
            "target_resource_code": record.target_resource_code,
            "target_schema_ref": record.target_schema_ref,
            "relation_type": record.relation_type,
            "relation_rule_json": copy.deepcopy(record.relation_rule_json),
            "source_evidence_ref": record.source_evidence_ref,
            "source_ref": record.source_evidence_ref,
            "generated_at": record.generated_at.isoformat(),
        }

    def _quality_record_to_dict(self, record: Any) -> dict[str, Any]:
        return {
            "quality_ref": record.quality_ref,
            "target_type": record.target_type,
            "target_ref": record.target_ref,
            "quality_status": record.quality_status,
            "score": record.score,
            "evidence_json": copy.deepcopy(record.evidence_json),
            "source_ref": record.source_ref,
            "generated_at": record.generated_at.isoformat(),
        }

    def _resource_asset_record_to_dict(self, record: Any) -> dict[str, Any]:
        return {
            "resource_code": record.resource_code,
            "resource_kind": record.resource_kind,
            "title": record.title,
            "lifecycle_status": record.lifecycle_status,
            "owner_org_id": record.owner_org_id,
            "owner_org_snapshot_json": _mask(copy.deepcopy(record.owner_org_snapshot_json)),
            "region_code": record.region_code,
            "catalog_code": record.catalog_code,
            "access_policy_json": _mask(copy.deepcopy(record.access_policy_json)),
            "qos_policy_json": copy.deepcopy(record.qos_policy_json),
            "source_ref": record.source_ref,
            "summary_json": _mask(copy.deepcopy(record.summary_json)),
        }

    def _binding_record_to_dict(self, record: Any) -> dict[str, Any]:
        return {
            "binding_code": record.binding_code,
            "resource_code": record.resource_code,
            "channel_kind": record.channel_kind,
            "route_ref": record.route_ref,
            "endpoint_ref": copy.deepcopy(record.endpoint_ref),
            "schema_ref": copy.deepcopy(record.schema_ref),
            "auth_ref": record.auth_ref,
            "request_schema_json": copy.deepcopy(record.request_schema_json),
            "response_schema_json": copy.deepcopy(record.response_schema_json),
            "gateway_policy_json": copy.deepcopy(record.gateway_policy_json),
            "lifecycle_status": record.lifecycle_status,
            "source_ref": record.source_ref,
        }

    def _api_test_projection_record_to_dict(self, record: Any) -> dict[str, Any]:
        return {
            "test_ref": record.test_ref,
            "resource_code": record.resource_code,
            "binding_code": record.binding_code,
            "test_result": record.test_result,
            "lifecycle_status": record.lifecycle_status,
            "source_ref": record.source_ref,
            "evidence_json": copy.deepcopy(record.evidence_json),
            "tested_by": record.tested_by,
            "tested_at": record.tested_at.isoformat(),
        }

    def _gateway_record_to_dict(self, record: Any) -> dict[str, Any]:
        return {
            "gateway_instance_id": record.gateway_instance_id,
            "runtime_profile": record.runtime_profile,
            "status": record.status,
            "last_reported_at": record.last_reported_at.isoformat(),
            "source_ref": record.source_ref,
            "summary_json": copy.deepcopy(record.summary_json),
            "generated_at": record.generated_at.isoformat(),
        }

    def _metric_record_to_dict(self, record: Any) -> dict[str, Any]:
        return {
            "metric_scope": record.metric_scope,
            "resource_code": record.resource_code,
            "capability_id": record.capability_id,
            "provider_org_id": record.provider_org_id,
            "consumer_org_id": record.consumer_org_id,
            "provider_region_code": record.provider_region_code,
            "consumer_region_code": record.consumer_region_code,
            "consumer_region": record.consumer_region,
            "consumer_app_ref": record.consumer_app_ref,
            "bucket_granularity": record.bucket_granularity,
            "time_bucket": record.time_bucket,
            "invoke_count": record.invoke_count,
            "success_count": record.success_count,
            "failed_count": record.failed_count,
            "provider_error_count": record.provider_error_count,
            "consumer_error_count": record.consumer_error_count,
            "gateway_error_count": record.gateway_error_count,
            "other_error_count": record.other_error_count,
            "error_count": record.error_count,
            "apply_count": record.apply_count,
            "avg_latency_ms": record.avg_latency_ms,
            "p95_latency_ms": record.p95_latency_ms,
            "last_error_code": record.last_error_code,
            "last_error_at": record.last_error_at.isoformat() if record.last_error_at else None,
            "source_event_ref": record.source_event_ref,
            "summary_json": copy.deepcopy(record.summary_json),
        }

    def create_request(self, resource_id: str, role: str, confirmed: bool, query: str = "", skill_id: str = "request.create") -> dict[str, Any]:
        resource = self._resolve_resource_for_application(resource_id)
        canonical_id = resource["id"]
        existing = next(
            (
                item
                for item in self._snapshot["requests"]
                if item.get("resourceId") == canonical_id and item["status"] in {"pending", "supplementing", "summary-pending"}
            ),
            None,
        )
        if existing is not None:
            raise InvalidStateError(f"active request already exists for resource {canonical_id}: {existing['id']}")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            request_id = self._new_request_id()
            task_id = self._delivery_task_id_for_request(request_id)
            query_text = query.strip() or self._ui_state.get("discoveryQuery") or DEFAULT_DISCOVERY_QUERY
            purpose = query_text or f"复用 {resource['name']}，仅补现场差异字段。"
            review_note = f"围绕 {resource['name']} 发起标准复用申请，待确认差异字段责任边界与回流要求。"
            request = {
                "id": request_id,
                "resourceId": canonical_id,
                "resourceName": resource["name"],
                "applicant": f"{actor}（市营商环境专班）" if role == "r1" else actor,
                "applicantDept": "市营商环境专班",
                "purpose": purpose,
                "range": "营商环境专题 · 镇街 / 社区协同",
                "expectedBy": (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d"),
                "status": "pending",
                "submittedAt": self._now_datetime(),
                "auditId": audit_id,
                "chainAnchor": "pending",
                "templateCoverage": resource.get("coverage", "—"),
                "prefilledFields": self._prefilled_fields_for_resource(resource),
                "diffFields": self._default_diff_fields(),
                "reviewFocus": [
                    "是否允许按模板先复用后补录",
                    "差异字段责任边界是否清楚",
                    "补录结果是否要求回流模板候选",
                ],
                "summaryResult": {
                    "totalEntities": 0,
                    "autoMerged": 0,
                    "exceptions": 0,
                    "note": "尚未进入基层任务；审批通过后才会生成预填任务与自动汇总链路。",
                },
                "returnFlow": [
                    "通过后自动创建镇街 / 社区预填任务",
                    "补录完成后自动生成汇总结果",
                    "高频差异字段进入回流候选池",
                ],
                "timeline": [
                    {
                        "label": "已发现可复用模板",
                        "time": self._now_datetime(),
                        "note": f"系统识别当前需求优先命中 {resource['name']}。",
                    },
                    {
                        "label": "已生成标准复用申请",
                        "time": self._now_datetime(),
                        "note": f"进入受控准入并生成 audit_id {audit_id}",
                    },
                    {
                        "label": "待审批承接人员判定",
                        "time": self._now_datetime(),
                        "note": review_note,
                    },
                    {
                        "label": "待基层补录",
                        "time": "—",
                        "note": "审批通过后自动下发预填任务。",
                    },
                    {
                        "label": "待审核汇总",
                        "time": "—",
                        "note": "系统先自动汇总，再由 R5 只处理异常项。",
                    },
                ],
                "aiDraft": {
                    "recognized": [
                        f"已识别起点：{resource['name']}",
                        "已识别策略：先复用再补差异字段",
                    ],
                    "needConfirm": [
                        "是否限定镇街 / 社区范围",
                        "是否需要把高频差异字段纳入回流候选",
                    ],
                    "missing": [
                        "现场经营状态是否需要逐家确认",
                        "是否要求附带走访备注",
                    ],
                    "risk": "若差异字段责任边界不清，后续会退回补正或增加基层重复填报。",
                    "attachments": [
                        "建议附“只补差异字段、不新增整表”的说明",
                        "建议明确补录完成后进入模板回流候选池",
                    ],
                    "summary": f"本申请拟优先复用 {resource['name']}，以共享资源池预填大部分基础字段，仅把现场差异字段交由基层补录。",
                },
                "aiStatus": {
                    "summary": f"申请已从资源发现页进入受控准入，当前围绕 {resource['name']} 等待 R2 判定差异边界。",
                    "nextAction": "建议审批承接人员先查看已预填字段与待补录字段，再决定是否下发基层任务。",
                    "evidence": [
                        f"模板覆盖率 {resource.get('coverage', '—')}",
                        "差异字段默认收敛为经营状态、走访时间和现场备注",
                        "已生成标准复用申请并进入受控准入",
                    ],
                },
            }
            approval = {
                "id": request_id,
                "suggestion": "建议通过",
                "confidence": 0.92,
                "reason": [
                    f"{resource['name']} 已覆盖多数基础字段",
                    "当前申请以差异补录替代新增整表，符合减负原则",
                    "回流要求可在后续链路中继续确认",
                ],
                "risk": [
                    "需明确经营状态由谁补录并谁来确认",
                    "需保留补录结果回流候选的责任边界",
                ],
                "counterfactual": "如果申请方绕开模板坚持新增整表，应转入补正或驳回。",
                "impact": "通过后将自动创建镇街 / 社区预填任务，并在补录完成后生成自动汇总结果。",
                "actions": ["通过", "退回补正", "驳回"],
                "draftNote": f"建议审批意见：同意以 {resource['name']} 作为预填底座，仅对现场差异字段发起补录；补录结果纳入回流候选。",
                "exceptionItems": [
                    "经营状态需明确由谁补录",
                    "走访备注是否纳入回流候选待确认",
                ],
                "autoSummary": "尚未进入自动汇总链；审批通过后会生成预填任务。",
            }
            delivery = {
                "id": task_id,
                "requestId": request_id,
                "name": f"{resource['name']} 预填任务下发与回流任务",
                "channel": "预填下发 + 汇总回流",
                "status": "warning",
                "owner": "市营商环境专班 → 镇街 / 社区 → 区县汇总",
                "updatedAt": self._now_datetime(),
                "note": "当前仍处于受控准入，审批通过后才会向基层下发预填任务。",
                "history": [
                    {
                        "time": self._now_short_time(),
                        "state": "申请生成",
                        "detail": "已从资源发现页进入标准复用申请，等待审批承接人员判定。",
                    }
                ],
                "aiSummary": {
                    "summary": "当前任务尚未下发基层；平台已把它约束在“先审批、再补录”的受控链路里。",
                    "nextAction": "请先由 R2 判定是否进入补录链路。",
                    "cause": "当前只是生成标准复用申请，还未形成基层责任动作。",
                    "impact": "避免绕过受控准入直接把任务甩给基层。",
                },
                "backflow": {
                    "candidateObject": "法人单位基础信息模板 v1.3",
                    "candidateFields": ["经营状态", "最近走访时间"],
                    "status": "待补录完成",
                    "note": "待审批、补录和汇总完成后，再决定是否纳入模板。",
                },
            }
            self._snapshot["requests"].insert(0, request)
            self._snapshot["approvals"].insert(0, approval)
            self._snapshot["delivery_tasks"].insert(0, delivery)
            self._append_audit_feed(skill_id, request_id, "ok", actor)
            return {"request_id": request_id, "status": request["status"]}

        return self._mutate(skill_id, role, confirmed, {"resource_id": resource_id, "query": query}, mutation)

    def submit_request(self, request_id: str, role: str, confirmed: bool) -> dict[str, Any]:
        request = self._request_by_id(request_id)
        if request["status"] != "need-fix":
            raise InvalidStateError("current request is not in resubmission state")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            request["status"] = "pending"
            request["submittedAt"] = self._now_datetime()
            request["auditId"] = audit_id
            request["chainAnchor"] = "pending"
            request["timeline"].append(
                {
                    "label": "已补齐后重新提交",
                    "time": self._now_datetime(),
                    "note": "申请已重新进入受控准入，等待审批承接人员判定。",
                }
            )
            request["aiStatus"]["summary"] = "申请已按“模板复用 + 差异补录”方式重新提交，当前重新回到受控准入阶段。"
            request["aiStatus"]["nextAction"] = "建议审批承接人员重新核对差异字段责任边界。"
            delivery = self._delivery_by_request_id(request_id)
            if delivery:
                delivery["status"] = "warning"
                delivery["updatedAt"] = self._now_datetime()
                delivery["note"] = "申请已重新提交，等待准入判定后再决定是否进入基层补录链路。"
                delivery["history"].append(
                    {
                        "time": self._now_short_time(),
                        "state": "重新提交待判定",
                        "detail": "补齐后重新进入受控准入，未直接下发基层任务。",
                    }
                )
                delivery["aiSummary"]["summary"] = "当前仍处于准入判定前，不应提前下发基层任务。"
                delivery["aiSummary"]["nextAction"] = "请先完成审批承接，再决定是否进入补录链路。"
            self._append_audit_feed("request.resubmit", request_id, "ok", actor)
            return {"request_id": request_id, "status": request["status"]}

        return self._mutate("request.submit", role, confirmed, {"request_id": request_id}, mutation)

    def review_request(self, request_id: str, decision: str, role: str, confirmed: bool, skill_id: str = "approval.review_decide") -> dict[str, Any]:
        if decision == "approve":
            return self._approve_request(request_id, role, confirmed, skill_id)
        if decision == "return_for_fix":
            return self._return_request_for_fix(request_id, role, confirmed, skill_id)
        if decision == "reject":
            return self._reject_request(request_id, role, confirmed, skill_id)
        raise BrainServiceError(f"unsupported review decision: {decision}")

    def submit_supplement(self, request_id: str, role: str, confirmed: bool) -> dict[str, Any]:
        request = self._request_by_id(request_id)
        if request["status"] != "supplementing":
            raise InvalidStateError("request is not in supplementing state")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            request["status"] = "summary-pending"
            request["diffFields"] = [
                {"label": "经营状态", "value": "正常经营", "reason": "现场状态变化快", "owner": "R3/R4 补录", "state": "已补录"},
                {"label": "最近走访时间", "value": self._now_date(), "reason": "共享池无现场时间", "owner": "R4 补录", "state": "已补录"},
                {"label": "现场备注", "value": "已完成走访核验，无新增异常。", "reason": "仅末端掌握", "owner": "R3/R4 补录", "state": "已补录"},
            ]
            request["summaryResult"]["note"] = "基层差异字段已全部回收，系统已生成自动汇总结果，待 R5 确认异常项。"
            request["timeline"].append(
                {
                    "label": "差异补录已提交",
                    "time": self._now_datetime(),
                    "note": "基层已提交现场差异字段，系统已自动进入汇总确认阶段。",
                }
            )
            request["aiStatus"]["summary"] = "差异补录已提交，系统已完成自动汇总并等待 R5 处理异常项。"
            request["aiStatus"]["nextAction"] = "请 R5 查看自动汇总结果并确认异常项。"
            delivery = self._delivery_by_request_id(request_id)
            if delivery:
                delivery["status"] = "reconciling"
                delivery["updatedAt"] = self._now_datetime()
                delivery["note"] = "基层补录已完成，自动汇总结果待审核汇总人员确认。"
                delivery["history"].append(
                    {
                        "time": self._now_short_time(),
                        "state": "基层补录完成",
                        "detail": "差异字段已回收，系统已生成汇总草稿和回流候选。",
                    }
                )
                delivery["aiSummary"]["summary"] = "链路已进入“自动汇总 → 异常确认 → 回流候选”阶段。"
                delivery["aiSummary"]["nextAction"] = "请 R5 确认异常项，再由 R6 / R7 决定是否纳入模板。"
                delivery["aiSummary"]["cause"] = "基层只补差异字段，因此系统可直接生成汇总结果。"
                delivery["aiSummary"]["impact"] = "确认完成后可把高频差异字段推进到模板治理侧。"
                delivery["backflow"]["status"] = "待确认"
                delivery["backflow"]["note"] = "差异字段已具备来源与责任方，待汇总确认后进入供给侧确认。"
            self._append_audit_feed("supplement.submit", request_id, "ok", actor)
            return {"request_id": request_id, "status": request["status"]}

        return self._mutate("supplement.submit", role, confirmed, {"request_id": request_id}, mutation)

    def confirm_summary(self, request_id: str, role: str, confirmed: bool) -> dict[str, Any]:
        request = self._request_by_id(request_id)
        if request["status"] != "summary-pending":
            raise InvalidStateError("request is not ready for summary confirmation")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            request["status"] = "completed"
            request["summaryResult"]["note"] = "R5 已确认自动汇总结果，链路进入回流候选确认。"
            request["timeline"].append(
                {
                    "label": "已确认自动汇总",
                    "time": self._now_datetime(),
                    "note": "异常项已处理完成，回流候选进入供给侧确认阶段。",
                }
            )
            request["aiStatus"]["summary"] = "自动汇总已确认，当前只剩回流候选是否正式纳入模板。"
            request["aiStatus"]["nextAction"] = "请 R6 / R7 确认回流候选并同步模板版本与专题入口。"
            delivery = self._delivery_by_request_id(request_id)
            if delivery:
                delivery["status"] = "reconciling"
                delivery["updatedAt"] = self._now_datetime()
                delivery["note"] = "汇总已确认，等待 R6 / R7 决定回流是否正式生效。"
                delivery["history"].append(
                    {
                        "time": self._now_short_time(),
                        "state": "汇总确认完成",
                        "detail": "异常项已由 R5 确认，任务转入回流确认。",
                    }
                )
                delivery["aiSummary"]["summary"] = "业务汇总已经闭环，当前重心转到模板治理和回流生效。"
                delivery["aiSummary"]["nextAction"] = "请确认是否把经营状态和最近走访时间纳入模板 v1.3。"
                delivery["aiSummary"]["cause"] = "自动汇总结果已被人工确认，可进入供给侧治理动作。"
                delivery["aiSummary"]["impact"] = "回流确认后，下次类似需求的基层补录字段会进一步下降。"
                delivery["backflow"]["status"] = "待确认"
                delivery["backflow"]["note"] = "回流候选已具备业务证据，待台账管理员与目录管理员确认。"
            self._append_audit_feed("summary.confirm", request_id, "ok", actor)
            return {"request_id": request_id, "status": request["status"]}

        return self._mutate("summary.confirm", role, confirmed, {"request_id": request_id}, mutation)

    def confirm_backflow(self, task_id: str, role: str, confirmed: bool) -> dict[str, Any]:
        task = self._delivery_by_id(task_id)
        request = self._request_by_id(task["requestId"])
        if request["status"] != "completed" or task.get("receiptStatus") != "reconciled" or task["backflow"]["status"] == "已确认":
            raise InvalidStateError("delivery task is not ready for backflow confirmation")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            task["status"] = "completed"
            task["updatedAt"] = self._now_datetime()
            task["note"] = "高频差异字段已确认纳入法人单位基础信息模板 v1.3。"
            task["history"].append(
                {
                    "time": self._now_short_time(),
                    "state": "回流确认完成",
                    "detail": "经营状态与最近走访时间已正式纳入模板 v1.3。",
                }
            )
            task["aiSummary"]["summary"] = "这条链路已经从一次性补录沉淀成下一次可直接复用的模板能力。"
            task["aiSummary"]["nextAction"] = "请回到 P5 / P7 检查模板版本与专题入口是否同步完成。"
            task["aiSummary"]["cause"] = "高频差异字段已经过一次真实业务验证，并具备明确来源与责任方。"
            task["aiSummary"]["impact"] = "下次类似需求将进一步减少基层补录工作量。"
            task["backflow"]["status"] = "已确认"
            task["backflow"]["note"] = "经营状态、最近走访时间已纳入法人单位基础信息模板 v1.3。"
            self._append_audit_feed("backflow.confirm", task["backflow"]["candidateObject"], "ok", actor)
            return {"task_id": task_id, "status": task["status"]}

        return self._mutate("backflow.confirm", role, confirmed, {"task_id": task_id}, mutation)

    def trigger_delivery_recovery(self, task_id: str, role: str, confirmed: bool) -> dict[str, Any]:
        task = self._delivery_by_id(task_id)
        if task["status"] != "failed":
            raise InvalidStateError("delivery task is not in failed state")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            task["status"] = "warning"
            task["updatedAt"] = self._now_datetime()
            task["note"] = "已触发恢复流程，等待审计链修复后重新对账。"
            task["history"].append(
                {
                    "time": self._now_short_time(),
                    "state": "恢复已触发",
                    "detail": "平台已显式登记恢复动作，等待后续重试与回执。",
                }
            )
            task["aiSummary"]["summary"] = "恢复动作已被显式触发，当前任务从失败态回到可追踪处理中间态。"
            task["aiSummary"]["nextAction"] = "请先修复审计链路，再重新执行补投和回执对账。"
            self._append_audit_feed("delivery.trigger-recovery", task_id, "ok", actor)
            return {"task_id": task_id, "status": task["status"]}

        return self._mutate("delivery.trigger_recovery", role, confirmed, {"task_id": task_id}, mutation)

    def configure_package_exposure(self, package_id: str, mode: str, role: str, confirmed: bool, skill_id: str = "package.configure_exposure") -> dict[str, Any]:
        item = self._package_by_id(package_id)
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
            self._append_audit_feed(skill_id, package_id, "ok", actor)
            return {"package_id": package_id, "exposure": next_exposure}

        return self._mutate(skill_id, role, confirmed, {"package_id": package_id, "mode": mode}, mutation)

    def investigate_dispute(self, dispute_id: str, action: str, role: str, confirmed: bool) -> dict[str, Any]:
        dispute = next((item for item in self._snapshot["disputes"] if item["id"] == dispute_id), None)
        if dispute is None:
            raise NotFoundError(dispute_id)
        if action not in {"progress", "escalate"}:
            raise BrainServiceError(f"unsupported dispute action: {action}")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            if action == "progress":
                dispute["timeline"].append(
                    {
                        "time": self._now_datetime(),
                        "label": "推进调查",
                        "note": "已补充核查当前绕行与责任链证据，等待进一步治理决定。",
                    }
                )
                dispute["aiSummary"] = "调查已推进：当前已补充责任链与证据核查，下一步判断是否需要升级到模板或制度治理。"
                self._set_todo_status("r8", dispute_id, "处理中")
                self._set_todo_status("r6", dispute_id, "待核查")
                event_type = "compliance.investigate-case"
            else:
                dispute["status"] = "escalated"
                dispute["owner"] = "区台账治理组"
                dispute["timeline"].append(
                    {
                        "time": self._now_datetime(),
                        "label": "升级治理",
                        "note": "已升级到模板治理与制度治理联动处置，要求供给侧与减负治理协同收口。",
                    }
                )
                dispute["aiSummary"] = "争议已升级：当前不再停留在个案调查，而是转入模板治理与制度治理联动处置。"
                self._set_todo_status("r8", dispute_id, "已升级")
                self._set_todo_status("r6", dispute_id, "已升级")
                event_type = "compliance.escalate-case"
            self._append_audit_feed(event_type, dispute_id, "ok", actor)
            return {"dispute_id": dispute_id, "status": dispute["status"], "action": action}

        return self._mutate("compliance.investigate_case", role, confirmed, {"dispute_id": dispute_id, "action": action}, mutation)

    def manage_catalog_entry(self, catalog_id: str, action: str, role: str, confirmed: bool) -> dict[str, Any]:
        provider = self._snapshot["provider"]
        catalog = next((item for item in provider["catalogs"] if item["id"] == catalog_id), None)
        if catalog is None:
            raise NotFoundError(catalog_id)
        if action == "publish":
            store = self._state_store.database_store
            if store is not None:
                store.catalog_repo.upsert_from_resource(
                    {
                        "id": catalog["id"],
                        "name": catalog.get("name", catalog["id"]),
                        "status": "approved_pending_publish",
                        "provider": catalog.get("owner", ""),
                        "source_ref": catalog.get("source_ref") or f"provider:catalog:{catalog['id']}",
                        "legacy_object_ref": catalog.get("legacy_object_ref") or catalog["id"],
                        "summary_json": catalog,
                    }
                )
        if action not in {"publish", "revise"}:
            raise InvalidStateError(f"unsupported catalog action: {action}")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            if action == "publish":
                catalog["status"] = "已发布"
                catalog["issue"] = f"已由 {actor} 完成目录发布确认"
                result = "published"
                event_type = "catalog.publish"
            else:
                catalog["issue"] = f"已由 {actor} 修正目录说明与默认复用入口文案"
                result = "revised"
                event_type = "catalog.revise"
            catalog["governanceLocked"] = True
            provider["aiGovernance"]["summary"] = "目录治理动作已落账，当前可继续推进资源状态和专区正式投影。"
            self._append_audit_feed(event_type, catalog_id, "ok", actor)
            return {"catalog_id": catalog_id, "status": catalog["status"], "result": result}

        return self._mutate("catalog.manage_entry", role, confirmed, {"catalog_id": catalog_id, "action": action}, mutation)

    def manage_resource_asset(self, resource_id: str, action: str, role: str, confirmed: bool) -> dict[str, Any]:
        provider = self._snapshot["provider"]
        resource = next((item for item in provider["resources"] if item["id"] == resource_id), None)
        if resource is None:
            raise NotFoundError(resource_id)
        store = self._state_store.database_store
        if action == "publish" and store is not None:
            store.resource_api_repo.upsert_asset(
                {
                    "resource_code": resource["id"],
                    "title": resource.get("name", resource["id"]),
                    "resource_kind": "dataset",
                    "lifecycle_status": "approved_pending_publish",
                    "owner_org_id": resource.get("owner_org_id"),
                    "source_ref": resource.get("source_ref") or f"provider:resource:{resource['id']}",
                    "legacy_object_ref": resource.get("legacy_object_ref") or resource["id"],
                    "summary_json": resource,
                }
            )
        if action == "suspend" and store is not None:
            store.resource_api_repo.transition_asset(resource_id, "suspended")
        if action not in {"publish", "suspend"}:
            raise InvalidStateError(f"unsupported resource action: {action}")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            if action == "publish":
                resource["status"] = "可共享"
                result = "published"
                event_type = "resource.publish"
            else:
                resource["status"] = "暂停共享"
                result = "suspended"
                event_type = "resource.suspend"
            resource["governanceLocked"] = True
            resource["updatedAt"] = self._now_date()
            provider["aiGovernance"]["summary"] = "资源治理状态已更新，当前应确认专区是否只消费可见资产。"
            self._append_audit_feed(event_type, resource_id, "ok", actor)
            return {"resource_id": resource_id, "status": resource["status"], "result": result}

        return self._mutate("resource.manage_asset", role, confirmed, {"resource_id": resource_id, "action": action}, mutation)

    def publish_zone_topic_projection(self, zone_id: str, role: str, confirmed: bool) -> dict[str, Any]:
        zone = self._zone_by_id(zone_id)

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            zone["status"] = "已发布"
            zone["projectionLocked"] = True
            if "模板版本：v1.3，默认入口已同步" not in zone.get("trust", []):
                zone.setdefault("trust", []).append("模板版本：v1.3，默认入口已同步")
            zone.setdefault("nextActions", [])
            if "继续作为默认复用入口" not in zone["nextActions"]:
                zone["nextActions"].insert(0, "继续作为默认复用入口")
            self._append_audit_feed("zone.publish-topic-projection", zone_id, "ok", actor)
            return {"zone_id": zone_id, "status": zone["status"]}

        return self._mutate("zone.publish_topic_projection", role, confirmed, {"zone_id": zone_id}, mutation)

    def grant_delivery_access(self, task_id: str, role: str, confirmed: bool) -> dict[str, Any]:
        task = self._delivery_by_id(task_id)
        if task["status"] not in {"pending", "warning", "reconciling", "supplementing"}:
            raise InvalidStateError("delivery task cannot grant access in current state")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            task["status"] = "completed"
            task["receiptStatus"] = task.get("receiptStatus") or "granted"
            task["updatedAt"] = self._now_datetime()
            task["note"] = "访问授权已生效，交付事实已写入可回放任务链。"
            task.setdefault("access", {})
            task["access"]["grant_ref"] = task["access"].get("grant_ref") or f"grant-{task_id}"
            task["access"]["status"] = "effective"
            task["history"].append(
                {
                    "time": self._now_short_time(),
                    "state": "授权已生效",
                    "detail": "核心审批后的授权交付已完成，并保留审计锚定。",
                }
            )
            task["aiSummary"]["summary"] = "访问授权已生效，当前可进入使用监测、回执对账或模板回流确认。"
            task["aiSummary"]["nextAction"] = "继续监测调用与回执，如存在高频差异字段再进入供给侧治理。"
            store = self._state_store.database_store
            if store is not None:
                store.delivery_repo.upsert_from_delivery(task, tenant_id=_DEFAULT_TENANT_ID)
            self._append_audit_feed("delivery.access.grant", task_id, "ok", actor)
            return {"task_id": task_id, "status": task["status"], "grant_ref": task["access"]["grant_ref"]}

        return self._mutate("delivery.access.grant", role, confirmed, {"task_id": task_id}, mutation)

    def reconcile_delivery_receipt(self, task_id: str, role: str, confirmed: bool) -> dict[str, Any]:
        task = self._delivery_by_id(task_id)
        if task["status"] == "failed":
            raise InvalidStateError("failed delivery task cannot be reconciled without recovery")
        if task.get("receiptStatus") == "reconciled":
            raise InvalidStateError("delivery receipt is already reconciled")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            task["receiptStatus"] = "reconciled"
            task["receiptNo"] = f"RCPT-{task_id.split('-')[-1]}"
            task["updatedAt"] = self._now_datetime()
            task["note"] = "交付回执已对账确认，当前可继续等待回流或治理动作。"
            task["history"].append(
                {
                    "time": self._now_short_time(),
                    "state": "回执已对账",
                    "detail": "平台已完成交付回执核对并保留审计留痕。",
                }
            )
            task["aiSummary"]["summary"] = "交付回执已完成对账，当前链路事实与外部回执保持一致。"
            task["aiSummary"]["nextAction"] = "如已满足业务门槛，可继续执行回流确认或供给侧治理动作。"
            self._append_audit_feed("delivery.reconcile-receipt", task_id, "ok", actor)
            return {"task_id": task_id, "receipt_status": task["receiptStatus"]}

        return self._mutate("delivery.reconcile_receipt", role, confirmed, {"task_id": task_id}, mutation)

    def publish_or_suspend_service(self, service_id: str, action: str, role: str, confirmed: bool) -> dict[str, Any]:
        provider = self._snapshot["provider"]
        service = next((item for item in provider["services"] if item["id"] == service_id), None)
        if service is None:
            raise NotFoundError(service_id)
        if action not in {"publish", "suspend"}:
            raise BrainServiceError(f"unsupported service action: {action}")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            if action == "publish":
                service["status"] = "在线"
                service["note"] = f"已由 {actor} 确认发布，保持对主旅程的稳定供给。"
                provider["aiGovernance"]["summary"] = "供给侧关键服务已发布，当前可继续推进模板版本与专区入口治理。"
                event_type = "service.publish"
                result = "published"
            else:
                service["status"] = "暂停"
                service["note"] = f"已由 {actor} 主动暂停，避免异常服务继续暴露到主旅程。"
                provider["aiGovernance"]["summary"] = "供给侧关键服务已暂停，需先完成核查后再重新发布。"
                event_type = "service.suspend"
                result = "suspended"
            provider["overview"][3]["value"] = str(sum(1 for item in provider["services"] if item["status"] != "在线"))
            self._append_audit_feed(event_type, service_id, "ok", actor)
            return {"service_id": service_id, "status": service["status"], "result": result}

        return self._mutate("service.publish_or_suspend", role, confirmed, {"service_id": service_id, "action": action}, mutation)

    def register_package_version(self, package_id: str, role: str, confirmed: bool, skill_id: str = "package.register_version") -> dict[str, Any]:
        item = self._package_by_id(package_id)
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
            self._append_audit_feed(skill_id, package_id, "ok", actor)
            return {"package_id": package_id, "registered_version": item["registeredVersion"]}

        return self._mutate(skill_id, role, confirmed, {"package_id": package_id}, mutation)

    def apply_package_tenant_policy(self, package_id: str, role: str, confirmed: bool, skill_id: str = "package.apply_tenant_policy", tenant_id: str = _DEFAULT_TENANT_ID) -> dict[str, Any]:
        item = self._package_by_id(package_id)
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
            store = self._state_store.database_store
            if store is not None:
                policy_record = store.capability_package_repo.upsert_tenant_policy(item | {"tenantPolicy": {"role_codes": [role]}}, tenant_id=tenant_id, exposed_surfaces=["api"])
                item["tenantPolicy"] = {
                    "tenantId": policy_record.tenant_id,
                    "policyStatus": policy_record.policy_status,
                    "policy": copy.deepcopy(policy_record.policy_json),
                }
            item["aiReview"]["summary"] = "租户策略已生效，能力包进入可控暴露状态；正式责任写动作仍然回到平台内建能力。"
            item["aiReview"]["draft"] = f"策略结论：{tenant_id} 租户已启用该能力包，暴露面与审计级别沿用已审核结果。"
            self._append_audit_feed(skill_id, package_id, "ok", actor)
            return {"package_id": package_id, "tenant_policy_status": item["tenantPolicy"]["policyStatus"], "tenant_id": tenant_id}

        return self._mutate(skill_id, role, confirmed, {"package_id": package_id, "tenant_id": tenant_id}, mutation)

    def review_package(self, package_id: str, decision: str, role: str, confirmed: bool, skill_id: str = "package.review_decide") -> dict[str, Any]:
        item = self._package_by_id(package_id)

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
                self._append_audit_feed("package.approve", package_id, "ok", actor)
            elif decision == "return_for_fix":
                item["status"] = "pending-fix"
                item["aiReview"]["summary"] = "该能力包需要先补齐租户范围或 side effects 声明，当前不进入上线。"
                self._append_audit_feed("package.return-for-fix", package_id, "warning", actor)
            elif decision == "reject":
                item["status"] = "rejected"
                item["aiReview"]["summary"] = "该能力包因越界写权或暴露面设计不合规被驳回。"
                item["aiReview"]["draft"] = "审核结论：驳回。请回到单一契约并撤销越界写权声明后再重新提交。"
                self._append_audit_feed("package.reject", package_id, "warning", actor)
            else:
                raise BrainServiceError(f"unsupported package decision: {decision}")
            return {"package_id": package_id, "status": item["status"]}

        return self._mutate(skill_id, role, confirmed, {"package_id": package_id, "decision": decision}, mutation)

    def register_capability_package(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))
        package_id = str(payload.get("package_id") or payload.get("id") or f"PKG-{payload['slug']}")
        slug = str(payload["slug"])

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            packages = self._snapshot.setdefault("capability_packages", [])
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
                "contract": self._safe_json(payload.get("contract") or {}),
                "tenantPolicy": self._safe_json(payload.get("tenantPolicy") or {"scope": "tenant-bound", "writeCanonicalState": False, "allowedWritebacks": []}),
                "failureWriteback": self._safe_json(payload.get("failureWriteback") or {"target": "audit_event", "mode": "failure_summary"}),
                "runtimeBinding": self._safe_json(payload.get("runtimeBinding") or {"protocol": "brain_service", "sideEffects": ["audit_only"]}),
            }
            if item is None:
                packages.append(package_payload)
            else:
                item.update(package_payload)
            store = self._state_store.database_store
            if store is not None:
                store.capability_package_repo.upsert_from_package(package_payload)
            self._append_audit_feed("capability.package.register", package_id, "ok", actor)
            return {"package_id": package_id, "slug": slug, "status": package_payload["status"], "audit_id": audit_id}

        return self._mutate("capability.package.register", role, confirmed, payload, mutation)

    def disable_tenant_capability(self, package_id: str, role: str, confirmed: bool, tenant_id: str = _DEFAULT_TENANT_ID) -> dict[str, Any]:
        item = self._package_by_id(package_id)

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
            store = self._state_store.database_store
            if store is not None:
                policy_record = store.capability_package_repo.set_tenant_policy_status(
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
            self._append_audit_feed("tenant.capability.disable", package_id, "ok", actor)
            return {"package_id": package_id, "tenant_policy_status": item["tenantPolicy"]["policyStatus"], "tenant_id": tenant_id, "audit_id": audit_id}

        return self._mutate("tenant.capability.disable", role, confirmed, {"package_id": package_id, "tenant_id": tenant_id}, mutation)

    def export_registry_artifacts(self) -> dict[str, Any]:
        manifests = self.manifests()
        packages = self.list_packages()
        return {"items": list(manifests.values()), "packages": packages, "total": len(manifests), "summary": {"skill_count": len(manifests), "package_count": len(packages)}}

    def toggle_outage(self, role: str, confirmed: bool) -> dict[str, Any]:
        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            self._ui_state["brainOutage"] = not self._ui_state["brainOutage"]
            self._append_audit_feed(
                "dashboard.snapshot-toggle",
                "brain",
                "warning" if self._ui_state["brainOutage"] else "ok",
                actor,
            )
            return {"brainOutage": self._ui_state["brainOutage"]}

        return self._mutate("system.toggle_outage", role, confirmed, {}, mutation)

    def _approve_request(self, request_id: str, role: str, confirmed: bool, skill_id: str = "approval.review_decide") -> dict[str, Any]:
        request = self._request_by_id(request_id)
        approval = self._approval_by_id(request_id)
        delivery = self._delivery_by_request_id(request_id)
        if request["status"] != "pending":
            raise InvalidStateError("current request cannot be approved")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            request["status"] = "supplementing"
            request["chainAnchor"] = "pending"
            request["timeline"].append(
                {
                    "label": "审批通过并下发补录",
                    "time": self._now_datetime(),
                    "note": "已进入镇街 / 社区差异补录阶段，基层只需补现场差异字段。",
                }
            )
            request["aiStatus"]["summary"] = "申请已通过准入判定，系统正在按模板预填并等待基层补录差异字段。"
            request["aiStatus"]["nextAction"] = "请 R3 / R4 核对预填字段后提交差异补录。"
            approval["suggestion"] = "建议通过"
            approval["impact"] = "已创建基层预填任务，待补录完成后进入自动汇总确认。"
            if delivery:
                delivery["status"] = "supplementing"
                delivery["updatedAt"] = self._now_datetime()
                delivery["note"] = "预填任务已下发，等待 R3 / R4 完成差异补录。"
                delivery["history"].append(
                    {
                        "time": self._now_short_time(),
                        "state": "预填任务已下发",
                        "detail": "系统已把共享模板字段下发到基层，只保留差异字段待补录。",
                    }
                )
                delivery["aiSummary"]["summary"] = "任务已进入“预填下发 → 差异补录”阶段，当前不需要人工拼表。"
                delivery["aiSummary"]["nextAction"] = "请基层完成经营状态、最近走访时间和现场备注补录。"
                delivery["aiSummary"]["cause"] = "审批已通过，模板字段可直接作为补录底座。"
                delivery["aiSummary"]["impact"] = "补录完成后会自动生成汇总结果并沉淀回流候选。"
                delivery["backflow"]["status"] = "待补录完成"
                delivery["backflow"]["note"] = "待基层补录和审核汇总完成后，再决定是否纳入模板。"
            self._append_audit_feed("request.approve", request_id, "ok", actor)
            return {"request_id": request_id, "status": request["status"]}

        return self._mutate(skill_id, role, confirmed, {"request_id": request_id, "decision": "approve"}, mutation)

    def _return_request_for_fix(self, request_id: str, role: str, confirmed: bool, skill_id: str = "approval.review_decide") -> dict[str, Any]:
        request = self._request_by_id(request_id)
        approval = self._approval_by_id(request_id)
        delivery = self._delivery_by_request_id(request_id)
        if request["status"] not in {"pending", "summary-pending"}:
            raise InvalidStateError("current request cannot be returned for fix")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            request["status"] = "need-fix"
            request["timeline"].append(
                {
                    "label": "已退回补正",
                    "time": self._now_datetime(),
                    "note": "要求重新说明差异字段责任边界或补齐异常项说明。",
                }
            )
            request["aiStatus"]["summary"] = "申请已退回补正，当前不进入下一状态。"
            request["aiStatus"]["nextAction"] = "请补齐差异字段说明后重新提交。"
            approval["suggestion"] = "建议补正"
            approval["impact"] = "退回补正后，补录与汇总链路暂停，不继续向前推进。"
            if delivery:
                delivery["status"] = "warning"
                delivery["updatedAt"] = self._now_datetime()
                delivery["note"] = "当前链路已退回补正，未继续推进补录或汇总。"
                delivery["history"].append(
                    {
                        "time": self._now_short_time(),
                        "state": "退回补正",
                        "detail": "因责任边界或异常项说明不足，链路暂停。",
                    }
                )
                delivery["aiSummary"]["summary"] = "这不是执行失败，而是人工决定链路回退补正。"
                delivery["aiSummary"]["nextAction"] = "请申请方或基层先补齐说明，再重新进入下一步。"
                delivery["backflow"]["status"] = "不适用"
                delivery["backflow"]["note"] = "当前未形成可确认的回流候选。"
            self._append_audit_feed("request.return-for-fix", request_id, "warning", actor)
            return {"request_id": request_id, "status": request["status"]}

        return self._mutate(skill_id, role, confirmed, {"request_id": request_id, "decision": "return_for_fix"}, mutation)

    def _reject_request(self, request_id: str, role: str, confirmed: bool, skill_id: str = "approval.review_decide") -> dict[str, Any]:
        request = self._request_by_id(request_id)
        delivery = self._delivery_by_request_id(request_id)
        if request["status"] not in {"pending", "summary-pending"}:
            raise InvalidStateError("current request cannot be rejected")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            request["status"] = "rejected"
            request["timeline"].append(
                {
                    "label": "已驳回申请",
                    "time": self._now_datetime(),
                    "note": "因重复要数或越界采集风险被终止。",
                }
            )
            request["aiStatus"]["summary"] = "该申请已被明确驳回，不再继续进入补录和汇总链路。"
            request["aiStatus"]["nextAction"] = "如需继续，请改为模板复用 + 差异补录模式重新发起。"
            if delivery:
                delivery["status"] = "warning"
                delivery["updatedAt"] = self._now_datetime()
                delivery["note"] = "申请已驳回，链路终止。"
                delivery["history"].append(
                    {
                        "time": self._now_short_time(),
                        "state": "申请驳回",
                        "detail": "因重复要数或越界采集风险，任务未继续推进。",
                    }
                )
                delivery["aiSummary"]["summary"] = "这是一次被明确终止的链路，不应伪装成业务成功。"
                delivery["aiSummary"]["nextAction"] = "如需重启，请先回到模板复用起点重新收敛需求。"
                delivery["backflow"]["status"] = "不适用"
                delivery["backflow"]["note"] = "驳回后不生成回流候选。"
            self._append_audit_feed("request.reject", request_id, "warning", actor)
            return {"request_id": request_id, "status": request["status"]}

        return self._mutate(skill_id, role, confirmed, {"request_id": request_id, "decision": "reject"}, mutation)

    def _resolve_role(self, payload: dict[str, Any]) -> str:
        try:
            return policy.resolve_role(payload.get("role"), self._ui_state.get("role", "r1"))
        except DomainAccessDeniedError as exc:
            raise AccessDeniedError(str(exc)) from exc

    def _enforce_manifest_policy(self, skill_id: str, manifest: dict[str, Any], role: str, payload: dict[str, Any]) -> None:
        try:
            policy.enforce_manifest_policy(skill_id, manifest, role, payload)
        except DomainAccessDeniedError as exc:
            raise AccessDeniedError(str(exc)) from exc

    def _invoke_traced_read(self, skill_id: str, role: str, payload: dict[str, Any], operation: Any) -> Any:
        store = self._state_store.database_store
        if store is None:
            return operation()
        actor = self._actor_for_role(role)
        audit_id = self._new_audit_id()
        started_at = datetime.now()
        self._emit_audit(audit_id, actor, skill_id, "before", payload)
        try:
            result = operation()
        except Exception as exc:
            self._emit_audit(audit_id, actor, skill_id, "error", {"error": exc.__class__.__name__, "message": str(exc)})
            self._record_capability_call(
                audit_id,
                actor,
                role,
                skill_id,
                payload,
                {"error": exc.__class__.__name__, "message": str(exc)},
                started_at,
                status="failed",
            )
            raise
        self._emit_audit(audit_id, actor, skill_id, "after", result if isinstance(result, dict) else {"result": result})
        self._record_capability_call(audit_id, actor, role, skill_id, payload, result if isinstance(result, dict) else {"result": result}, started_at)
        return result

    def _mutate(self, skill_id: str, role: str, confirmed: bool, payload: dict[str, Any], mutation: Any) -> dict[str, Any]:
        manifest = get_manifest(skill_id)
        self._enforce_manifest_policy(skill_id, manifest, role, payload | {"confirmed": confirmed})
        if manifest.get("human_confirmation_required") and not confirmed:
            raise ConfirmationRequiredError(skill_id)
        actor = self._actor_for_role(role)
        audit_id = self._new_audit_id()
        started_at = datetime.now()
        self._emit_audit(audit_id, actor, skill_id, "before", payload)
        try:
            result = mutation(audit_id, actor)
        except Exception as exc:
            self._emit_audit(audit_id, actor, skill_id, "error", {"error": exc.__class__.__name__, "message": str(exc)})
            self._record_capability_call(
                audit_id,
                actor,
                role,
                skill_id,
                payload,
                {"error": exc.__class__.__name__, "message": str(exc)},
                started_at,
                status="failed",
            )
            raise
        self._sync_state_views()
        self._persist()
        self._emit_audit(audit_id, actor, skill_id, "after", result)
        self._record_capability_call(audit_id, actor, role, skill_id, payload, result, started_at)
        if manifest.get("side_effects"):
            self._sync_database_aggregates()
            self._enqueue_anchor(audit_id, actor, skill_id, payload | result)
        return {"ok": True, "skill_id": skill_id, "audit_id": audit_id, "result": result}

    def _record_capability_call(
        self,
        audit_id: str,
        actor: str,
        role: str,
        skill_id: str,
        payload: dict[str, Any],
        result: dict[str, Any],
        started_at: datetime,
        *,
        status: str = "succeeded",
    ) -> None:
        store = self._state_store.database_store
        if store is None:
            return
        store.append_capability_call(
            {
                "call_ref": audit_id,
                "tenant_id": str(payload.get("tenant_id", _DEFAULT_TENANT_ID)),
                "skill_id": skill_id,
                "actor": actor,
                "role_code": role,
                "status": status,
                "request_ref": self._audit_target_from_payload(audit_id, payload),
                "input_json": safe_json(payload),
                "output_json": safe_json(result),
                "started_at": started_at,
                "completed_at": datetime.now(),
            }
        )

    def _persist(self) -> None:
        self._state_store.save(self._snapshot, self._ui_state)

    def _emit_audit(self, request_id: str, actor: str, skill_id: str, phase: str, payload: dict[str, Any]) -> None:
        manifest = get_manifest(skill_id)
        actor_parts = actor.split(":", 3)
        payload_with_evidence = safe_json(payload)
        if isinstance(payload_with_evidence.get("actor_snapshot"), dict) and payload_with_evidence["actor_snapshot"]:
            actor_snapshot = copy.deepcopy(payload_with_evidence["actor_snapshot"])
        else:
            actor_snapshot = {"actor": actor}
            if len(actor_parts) >= 3 and actor_parts[:2] == ["user", "gov"]:
                actor_snapshot["role_code"] = actor_parts[2]
        payload_with_evidence["skill_id"] = skill_id
        payload_with_evidence["audit_class"] = payload_with_evidence.get("audit_class") or manifest.get("audit_class")
        payload_with_evidence["actor_snapshot"] = actor_snapshot
        payload_with_evidence["policy_version"] = payload_with_evidence.get("policy_version") or manifest.get("version")
        payload_with_evidence["decision_reason"] = payload_with_evidence.get("decision_reason") or self._audit_decision_reason(phase, payload)
        payload_with_evidence["target_ref"] = payload_with_evidence.get("target_ref") or self._audit_target_from_payload(request_id, payload)
        audit_bus.emit(
            audit_bus.AuditEvent(
                request_id=request_id,
                actor=actor,
                skill_id=skill_id,
                phase=phase,
                payload=payload_with_evidence,
            )
        )

    def _audit_decision_reason(self, phase: str, payload: dict[str, Any]) -> str:
        value = payload.get("decision_reason") or payload.get("decision") or payload.get("error") or phase
        return str(value)

    def _enqueue_anchor(self, request_id: str, actor: str, skill_id: str, payload: dict[str, Any]) -> None:
        content_hash = hashlib.sha256(
            json.dumps(
                {
                    "request_id": request_id,
                    "actor": actor,
                    "skill_id": skill_id,
                    "payload": payload,
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        store = self._state_store.database_store
        if store is not None:
            store.append_anchor_outbox(request_id, skill_id, content_hash, "mock-chain")
        asyncio.run(
            queue.enqueue(
                "blockchain.anchor",
                {
                    "request_id": request_id,
                    "skill_id": skill_id,
                    "actor": actor,
                    "content_hash": content_hash,
                    "chain_id": "mock-chain",
                },
            )
        )

    def _sync_reference_tables(self) -> None:
        store = self._state_store.database_store
        if store is None:
            return
        store.sync_reference_tables(self.snapshot())

    def _sync_database_aggregates(self) -> None:
        store = self._state_store.database_store
        if store is None:
            return
        store.sync_aggregate_tables(self.snapshot())

    def _append_audit_feed(self, event_type: str, target: str, result: str, actor: str) -> None:
        self._snapshot["audit_events"].append(
            {
                "id": self._new_audit_id(),
                "time": self._month_day_time(),
                "actor": actor,
                "type": event_type,
                "target": target,
                "result": result,
                "chain": "pending" if result != "failed" else "n/a",
            }
        )

    def _audit_target_from_payload(self, request_id: str, payload: dict[str, Any]) -> str:
        for field in (
            "dispute_id",
            "request_id",
            "task_id",
            "package_id",
            "resource_id",
            "catalog_id",
            "catalog_code",
            "resource_code",
            "service_id",
            "zone_id",
            "target_ref",
            "id",
        ):
            value = payload.get(field)
            if value:
                return str(value)
        return request_id

    def _sync_state_views(self) -> None:
        self._sync_request_todos()
        request0011 = self._maybe_request("REQ-2026-04-25-0011")
        request0007 = self._maybe_request("REQ-2026-04-24-0007")
        task0011 = self._maybe_delivery("DLV-2026-04-25-0011")
        package001 = self._maybe_package("PKG-2026-04-25-001")

        if request0011:
            self._set_todo_status("r1", "REQ-2026-04-25-0011", self._request_status_text(request0011, "r1"))
            self._set_todo_status("r2", "REQ-2026-04-25-0011", self._request_status_text(request0011, "r2"))
            self._set_todo_status("r3", "REQ-2026-04-25-0011", self._request_status_text(request0011, "r3"))
            self._set_todo_status("r4", "REQ-2026-04-25-0011", self._request_status_text(request0011, "r4"))
            self._set_todo_status("r5", "REQ-2026-04-25-0011", self._request_status_text(request0011, "r5"))
        if request0007:
            self._set_todo_status("r2", "REQ-2026-04-24-0007", self._request_status_text(request0007, "r2"))
            self._set_todo_status("r3", "REQ-2026-04-24-0007", self._request_status_text(request0007, "r3"))

        if task0011:
            confirmed = task0011["backflow"]["status"] == "已确认"
            self._set_todo_status("r6", "LEDGER-jbxx-v1.3", "已发布" if confirmed else "待发布")
            self._set_todo_status("r7", "ZONE-business-ledger", "已上线" if confirmed else "待更新")
            provider = self._snapshot["provider"]
            provider["overview"][0]["value"] = "v1.3" if confirmed else "v1.2 → v1.3"
            provider["overview"][2]["value"] = "0" if confirmed else str(len(task0011["backflow"]["candidateFields"]))
            provider["catalogs"][0]["issue"] = "v1.3 版本说明已同步" if confirmed else "需补充 v1.3 版本说明"
            if not provider["catalogs"][1].get("governanceLocked"):
                provider["catalogs"][1]["status"] = "已发布" if confirmed else "待质检"
                provider["catalogs"][1]["issue"] = "默认复用入口已更新" if confirmed else "需更新默认复用入口说明"
            provider["resources"][0]["updatedAt"] = self._now_date() if confirmed else "2026-04-25"
            if not provider["resources"][1].get("governanceLocked"):
                provider["resources"][1]["status"] = "可共享" if confirmed else "待审核"
            provider["aiGovernance"]["summary"] = (
                "法人模板 v1.3 已确认吸收高频差异字段，下一步重点转为持续监测补录热区和维护专题入口一致性。"
                if confirmed
                else "建议优先发布法人模板 v1.3，并把“经营状态”“最近走访时间”纳入正式字段候选；其次更新营商环境专题目录中的默认复用入口说明。"
            )
            discovery = self._resource_by_id("res-jbxx-ledger")
            discovery["coverage"] = "89%" if confirmed else "82%"
            discovery["updatedAt"] = self._now_date() if confirmed else "2026-04-25"
            discovery["explain"] = [
                "当前需求可直接复用 v1.3 模板，基层补录字段进一步收缩",
                "经营状态与最近走访时间已纳入正式字段",
                "专题入口与模板版本已同步更新",
            ] if confirmed else [
                "当前需求首先应复用该模板，而不是重新发起整表采集",
                "模板已覆盖多数企业基础字段",
                "仅需补少量现场差异字段即可形成任务",
            ]
            zone = self._zone_by_id("business")
            zone["trust"] = [
                "来源等级：高",
                "模板版本：v1.3，默认入口已同步",
                "责任方：区政数局 / 市场监管局",
            ] if confirmed else [
                "来源等级：高",
                "模板版本：v1.2，v1.3 待发布",
                "责任方：区政数局 / 市场监管局",
            ]
            dashboard = self._snapshot["dashboard"]
            dashboard["summary"]["alerts"] = "1" if confirmed else "2"
            dashboard["burdenMetrics"][1]["value"] = "1 / 单任务" if confirmed else "3 / 单任务"
            dashboard["burdenMetrics"][1]["trend"] = "较基线 -84%" if confirmed else "较基线 -72%"
            dashboard["burdenMetrics"][2]["value"] = "96%" if confirmed else "93%"
            dashboard["burdenMetrics"][2]["trend"] = "较上周 +14pt" if confirmed else "较上周 +11pt"
            dashboard["burdenMetrics"][3]["value"] = "0" if confirmed else "2"
            dashboard["burdenMetrics"][3]["trend"] = "已纳入模板" if confirmed else "本周新增"
            dashboard["suggestions"]["body"] = (
                "当前黄金链路已经闭环到模板升级，基层补录字段明显收缩。下一步重点盯住仍绕开模板发起采集的部门。"
                if confirmed
                else "当前黄金链路已经跑通，但仍有部门绕开法人模板发起新增采集，同时经营状态字段持续高频补录，建议优先做制度提醒和模板升级。"
            )
            dashboard["suggestions"]["evidence"] = [
                "经营状态与最近走访时间已并入模板 v1.3",
                "基层补录字段数已下降到 1 / 单任务",
                "仍有 1 条绕行类告警需要制度治理",
            ] if confirmed else [
                "本周重复要数率已降至 12%，但仍有 1 条高风险绕行告警",
                "经营状态字段近 7 日补录 14 次",
                "法人模板复用后基层填报时长下降 31%",
            ]
            dashboard["suggestions"]["nextAction"] = "继续盯住绕行告警并复盘专题入口执行情况。" if confirmed else "先看绕行告警，再推动模板 v1.3 升级。"

        if package001:
            self._set_todo_status("r7", "PKG-2026-04-25-001", self._package_status_text(package001))

    def _set_todo_status(self, role: str, item_id: str, status: str) -> None:
        bucket = self._snapshot["workbench"].get(role)
        if not bucket:
            return
        for todo in bucket["todos"]:
            if todo["id"] == item_id:
                todo["status"] = status
                return

    def _request_status_text(self, item: dict[str, Any], role: str) -> str:
        if item["status"] == "pending":
            return "审批中" if role == "r1" else "待审批"
        if item["status"] == "supplementing":
            return "待补录" if role in {"r3", "r4"} else "补录中"
        if item["status"] == "summary-pending":
            return "待汇总确认"
        if item["status"] == "completed":
            return "已汇总"
        if item["status"] == "need-fix":
            return "待补正"
        if item["status"] == "rejected":
            return "已驳回"
        return str(item["status"])

    def _package_status_text(self, item: dict[str, Any]) -> str:
        if item["status"] == "pending":
            return "待审核"
        if item["status"] == "pending-fix":
            return "待补正"
        if item["status"] == "approved":
            return "已上线"
        if item["status"] == "rejected":
            return "已驳回"
        return str(item["status"])

    def _actor_for_role(self, role: str) -> str:
        try:
            return policy.actor_for_role(role)
        except DomainAccessDeniedError as exc:
            raise AccessDeniedError(str(exc)) from exc

    def _request_by_id(self, request_id: str) -> dict[str, Any]:
        for item in self._snapshot["requests"]:
            if item["id"] == request_id:
                return item
        raise NotFoundError(request_id)

    def _maybe_request(self, request_id: str) -> dict[str, Any] | None:
        try:
            return self._request_by_id(request_id)
        except NotFoundError:
            return None

    def _approval_by_id(self, request_id: str) -> dict[str, Any]:
        for item in self._snapshot["approvals"]:
            if item["id"] == request_id:
                return item
        raise NotFoundError(request_id)

    def _delivery_by_request_id(self, request_id: str) -> dict[str, Any] | None:
        for item in self._snapshot["delivery_tasks"]:
            if item["requestId"] == request_id:
                return item
        return None

    def _delivery_by_id(self, task_id: str) -> dict[str, Any]:
        for item in self._snapshot["delivery_tasks"]:
            if item["id"] == task_id:
                return item
        raise NotFoundError(task_id)

    def _maybe_delivery(self, task_id: str) -> dict[str, Any] | None:
        try:
            return self._delivery_by_id(task_id)
        except NotFoundError:
            return None

    def _resource_by_id(self, resource_id: str) -> dict[str, Any]:
        for item in self._snapshot["discovery"]["resources"]:
            if item["id"] == resource_id:
                return item
        raise NotFoundError(resource_id)

    def _resolve_resource_for_application(self, resource_id: str) -> dict[str, Any]:
        """Resolve catalog/provider aliases (e.g. cat-parking) to canonical discovery.resources rows."""
        try:
            return copy.deepcopy(self._resource_by_id(resource_id))
        except NotFoundError:
            pass

        store = self._state_store.database_store
        catalog_record = store.catalog_repo.get_entry(resource_id, tenant_id=_DEFAULT_TENANT_ID) if store is not None else None

        summary: dict[str, Any] = {}
        if catalog_record is not None:
            sr = catalog_record.summary_json
            summary = sr if isinstance(sr, dict) else {}

        provider_cat = next(
            (c for c in self._snapshot.get("provider", {}).get("catalogs", []) if c.get("id") == resource_id),
            None,
        )

        canonical_id = (
            summary.get("canonical_resource_id")
            or summary.get("application_resource_id")
            or (provider_cat or {}).get("canonical_resource_id")
            or (provider_cat or {}).get("application_resource_id")
        )
        if canonical_id:
            try:
                return copy.deepcopy(self._resource_by_id(str(canonical_id)))
            except NotFoundError as exc:
                raise BrainServiceError(
                    f"catalog {resource_id!r} declares canonical_resource_id {canonical_id!r} but no matching discovery.resources entry exists"
                ) from exc

        legacy_ref = summary.get("legacy_object_ref") or summary.get("legacyId")
        if provider_cat:
            legacy_ref = legacy_ref or provider_cat.get("legacy_object_ref")

        if legacy_ref:
            matches = [
                item
                for item in self._snapshot["discovery"]["resources"]
                if (item.get("trueData") or {}).get("catalog_code") == legacy_ref or item.get("legacyId") == legacy_ref
            ]
            if len(matches) == 1:
                return copy.deepcopy(matches[0])
            if len(matches) > 1:
                raise BrainServiceError(
                    f"ambiguous legacy mapping for catalog or alias {resource_id!r}: {len(matches)} discovery.resources "
                    f"match legacy_object_ref {legacy_ref!r}; set canonical_resource_id on the catalog entry to a single discovery.resources id"
                )

        if catalog_record is not None:
            cc = catalog_record.catalog_code
            matches = [
                item
                for item in self._snapshot["discovery"]["resources"]
                if (item.get("trueData") or {}).get("catalog_code") == cc
            ]
            if len(matches) == 1:
                return copy.deepcopy(matches[0])
            if len(matches) > 1:
                raise BrainServiceError(
                    f"ambiguous catalog_code mapping for {resource_id!r}: {len(matches)} resources share catalog_code {cc!r}; "
                    f"set canonical_resource_id on the catalog entry"
                )

        raise NotFoundError(resource_id)

    def _package_by_id(self, package_id: str) -> dict[str, Any]:
        for item in self._snapshot["capability_packages"]:
            if item["id"] == package_id:
                return item
        raise NotFoundError(package_id)

    def _maybe_package(self, package_id: str) -> dict[str, Any] | None:
        try:
            return self._package_by_id(package_id)
        except NotFoundError:
            return None

    def _zone_by_id(self, zone_id: str) -> dict[str, Any]:
        for item in self._snapshot["zones"]:
            if item["id"] == zone_id:
                return item
        raise NotFoundError(zone_id)


    def _upsert_todo(self, role: str, item_id: str, title: str, status: str, href: str) -> None:
        bucket = self._snapshot["workbench"].get(role)
        if not bucket:
            return
        for todo in bucket["todos"]:
            if todo["id"] == item_id:
                todo["title"] = title
                todo["status"] = status
                todo["href"] = href
                return
        bucket["todos"].insert(0, {"id": item_id, "title": title, "status": status, "href": href})

    def _sync_request_todos(self) -> None:
        for request in self._snapshot["requests"]:
            request_id = request["id"]
            resource_name = request.get("resourceName", request_id)
            self._upsert_todo("r1", request_id, f"{resource_name}复用申请进度跟踪", self._request_status_text(request, "r1"), f"#/p3-request-flow/request/{request_id}")
            self._upsert_todo("r2", request_id, f"{resource_name}复用申请待判定", self._request_status_text(request, "r2"), f"#/p3-request-flow/review/{request_id}")
            if request["status"] in {"supplementing", "summary-pending", "completed", "need-fix"}:
                self._upsert_todo("r3", request_id, f"{resource_name}差异补录任务", self._request_status_text(request, "r3"), f"#/p3-request-flow/request/{request_id}")
                self._upsert_todo("r4", request_id, f"{resource_name}现场补录任务", self._request_status_text(request, "r4"), f"#/p3-request-flow/request/{request_id}")
            if request["status"] in {"pending", "summary-pending", "completed", "need-fix", "rejected"}:
                self._upsert_todo("r5", request_id, f"{resource_name}汇总/准入处理", self._request_status_text(request, "r5"), f"#/p3-request-flow/review/{request_id}")

    def _new_request_id(self) -> str:
        prefix = f"REQ-{datetime.now():%Y-%m-%d}-"
        seq = 1
        for item in self._snapshot["requests"]:
            item_id = str(item.get("id", ""))
            if item_id.startswith(prefix):
                try:
                    seq = max(seq, int(item_id.rsplit("-", 1)[-1]) + 1)
                except ValueError:
                    continue
        return f"{prefix}{seq:04d}"

    def _delivery_task_id_for_request(self, request_id: str) -> str:
        return request_id.replace("REQ-", "DLV-", 1)

    def _prefilled_fields_for_resource(self, resource: dict[str, Any]) -> list[dict[str, Any]]:
        samples = {
            "统一社会信用代码": "91370000MA3XXXXXX1",
            "企业名称": "山东云启科技有限公司",
            "法定代表人": "李某某",
            "行业代码": "I6510",
            "成立日期": "2020-08-18",
            "登记机关": "市市场监管局",
            "经营场所": "高新区软件园 A 座",
            "注册资本": "500 万元",
        }
        fields = []
        for field in resource.get("fields", [])[:5]:
            fields.append(
                {
                    "label": field,
                    "value": samples.get(field, "已带出"),
                    "source": "共享资源池 / 模板预填",
                    "state": "已预填",
                }
            )
        return fields

    def _default_diff_fields(self) -> list[dict[str, Any]]:
        return [
            {
                "label": "经营状态",
                "value": "待镇街确认",
                "reason": "现场状态变化快",
                "owner": "R3/R4 补录",
            },
            {
                "label": "最近走访时间",
                "value": "待补录",
                "reason": "共享池无现场时间",
                "owner": "R4 补录",
            },
            {
                "label": "现场备注",
                "value": "待补录",
                "reason": "仅末端掌握",
                "owner": "R3/R4 补录",
            },
        ]

    def _new_audit_id(self) -> str:
        now = datetime.now()
        return f"AE-{now:%Y-%m-%d-%H%M%S%f}"

    def _month_day_time(self) -> str:
        return datetime.now().strftime("%m-%d %H:%M")

    def _now_date(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def _now_datetime(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M")

    def _now_short_time(self) -> str:
        return datetime.now().strftime("%H:%M")
