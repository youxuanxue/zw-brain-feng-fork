from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from datetime import datetime, timedelta
from typing import Any

import zw_brain.shared.audit as audit_bus
from zw_brain.domain import policy
from zw_brain.domain.policy import DomainAccessDeniedError
from zw_brain.domain.schemas import describe_schemas
from zw_brain.shared import queue
from zw_brain.shared.sanitization import safe_json
from zw_brain.shared.state_store import StateStore
from zw_brain.skill_registration.runtime import get_manifest, load_manifests

DEFAULT_DISCOVERY_QUERY = "我要为本周营商环境专题复用法人单位基础信息台账模板，优先自动带出企业基础字段，只补现场差异字段。"


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
        return state

    def manifests(self) -> dict[str, dict[str, Any]]:
        return load_manifests()

    def invoke_skill(self, skill_id: str, payload: dict[str, Any] | None = None) -> Any:
        payload = payload or {}
        try:
            manifest = get_manifest(skill_id)
        except KeyError as exc:
            raise UnknownSkillError(skill_id) from exc
        role = self._resolve_role(payload)
        self._ui_state["role"] = role
        self._enforce_manifest_policy(skill_id, manifest, role, payload)

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
            case "resource.api.register":
                return self.register_api_resource(payload)
            case "resource.api.change":
                return self.change_api_resource(payload)
            case "resource.api.submit_review":
                return self.submit_api_resource_review(str(payload["resource_code"]), str(payload.get("role", self._ui_state["role"])), bool(payload.get("confirmed")))
            case "resource.api.review":
                return self.review_api_resource(str(payload["resource_code"]), str(payload["decision"]), str(payload.get("role", self._ui_state["role"])), bool(payload.get("confirmed")))
            case "resource.api.publish":
                return self.transition_api_resource(str(payload["resource_code"]), "published", "resource.api.publish", str(payload.get("role", self._ui_state["role"])), bool(payload.get("confirmed")))
            case "resource.api.withdraw":
                return self.transition_api_resource(str(payload["resource_code"]), "withdrawn", "resource.api.withdraw", str(payload.get("role", self._ui_state["role"])), bool(payload.get("confirmed")))
            case "resource.api.revoke":
                return self.transition_api_resource(str(payload["resource_code"]), "revoked", "resource.api.revoke", str(payload.get("role", self._ui_state["role"])), bool(payload.get("confirmed")))
            case "resource.api.test":
                return self.test_api_resource(payload)
            case "resource.api.policy.update":
                return self.update_api_resource_policy(payload)
            case "system.snapshot":
                return self.snapshot()
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

    def get_workbench(self, role: str) -> dict[str, Any]:
        if role not in self._snapshot["workbench"]:
            raise NotFoundError(role)
        return copy.deepcopy(self._snapshot["workbench"][role])

    def list_requests(self) -> list[dict[str, Any]]:
        items = copy.deepcopy(self._snapshot["requests"])
        store = self._state_store.database_store
        if store is None:
            return items
        records = {record.application_code: record for record in store.application_repo.list_records()}
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
                item["repositoryPolicy"] = {
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
        records = {record.delivery_code: record for record in store.delivery_repo.list_tasks()}
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
            records = {record.id: record for record in store.objection_repo.list_cases()}
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
        resource = copy.deepcopy(self._resource_by_id(resource_id))
        store = self._state_store.database_store
        if store is None:
            return resource
        record = store.catalog_repo.get_entry(resource_id)
        if record is not None:
            resource = copy.deepcopy(record.summary_json)
            resource["id"] = record.catalog_code
            resource["name"] = record.title
            resource["status"] = record.lifecycle_status
            if record.owner_org_id:
                resource["provider"] = record.owner_org_id
            resource["repository"] = {
                "catalogCode": record.catalog_code,
                "lifecycleStatus": record.lifecycle_status,
                "ownerOrgId": record.owner_org_id,
            }
        return resource

    def get_request(self, request_id: str) -> dict[str, Any]:
        request = copy.deepcopy(self._request_by_id(request_id))
        store = self._state_store.database_store
        if store is None:
            return request
        for record in store.application_repo.list_records():
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
        case = next((item for item in store.approval_repo.list_cases() if item.application_code == request_id), None)
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
        record = next((item for item in store.delivery_repo.list_tasks() if item.delivery_code == task_id), None)
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
        package.setdefault("compatibility", package.get("exposure", []))
        package.setdefault("tenantScope", "default")
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
            "serviceFailureCount": service_report["summary"]["failureCount"],
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
                if not haystack or haystack in text or any(token in query for token in ["法人", "企业", "模板", "复用"]):
                    resources.append(copy.deepcopy(item))
        else:
            records = store.catalog_repo.search_entries(query)
            resources = []
            for record in records:
                item = copy.deepcopy(record.summary_json)
                item["id"] = record.catalog_code
                item["name"] = record.title
                item["status"] = record.lifecycle_status
                if record.owner_org_id:
                    item["provider"] = record.owner_org_id
                item["repository"] = {
                    "catalogCode": record.catalog_code,
                    "lifecycleStatus": record.lifecycle_status,
                    "ownerOrgId": record.owner_org_id,
                }
                resources.append(item)
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
                "failureCount": metric_summary["failureCount"],
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

    def submit_api_resource_review(self, resource_code: str, role: str, confirmed: bool) -> dict[str, Any]:
        return self.transition_api_resource(resource_code, "review_pending", "resource.api.submit_review", role, confirmed)

    def review_api_resource(self, resource_code: str, decision: str, role: str, confirmed: bool) -> dict[str, Any]:
        if decision == "approve":
            return self.transition_api_resource(resource_code, "approved", "resource.api.review", role, confirmed)
        if decision == "return_for_fix":
            return self.transition_api_resource(resource_code, "draft", "resource.api.review", role, confirmed)
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
                if status == "published" and record.catalog_code:
                    store.catalog_repo.upsert_from_resource(
                        {
                            "id": record.catalog_code,
                            "name": record.title,
                            "status": "published",
                            "provider": record.owner_org_id or "",
                            "resource_code": record.resource_code,
                            "source_ref": record.source_ref,
                            "legacy_object_ref": record.resource_code,
                            "desc": record.summary_json.get("desc") or record.summary_json.get("title") or record.title,
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
            "catalog_code": payload.get("catalog_code"),
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
            "failureCount": sum(int(item.get("failure_count", 0)) for item in metrics),
            "errorCount": sum(int(item.get("error_count", 0)) for item in metrics),
        }

    def _safe_json(self, value: dict[str, Any]) -> dict[str, Any]:
        return safe_json(value)

    def _resource_asset_record_to_dict(self, record: Any) -> dict[str, Any]:
        return {
            "resource_code": record.resource_code,
            "resource_kind": record.resource_kind,
            "title": record.title,
            "lifecycle_status": record.lifecycle_status,
            "owner_org_id": record.owner_org_id,
            "catalog_code": record.catalog_code,
            "source_ref": record.source_ref,
            "summary_json": copy.deepcopy(record.summary_json),
        }

    def _binding_record_to_dict(self, record: Any) -> dict[str, Any]:
        return {
            "binding_code": record.binding_code,
            "resource_code": record.resource_code,
            "channel_kind": record.channel_kind,
            "route_ref": record.route_ref,
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
            "gateway_address_ref": record.gateway_address_ref,
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
            "consumer_region": record.consumer_region,
            "consumer_app_ref": record.consumer_app_ref,
            "time_bucket": record.time_bucket,
            "invoke_count": record.invoke_count,
            "success_count": record.success_count,
            "failure_count": record.failure_count,
            "error_count": record.error_count,
            "avg_latency_ms": record.avg_latency_ms,
            "source_event_ref": record.source_event_ref,
            "summary_json": copy.deepcopy(record.summary_json),
        }

    def create_request(self, resource_id: str, role: str, confirmed: bool, query: str = "") -> dict[str, Any]:
        resource = self._resource_by_id(resource_id)
        existing = next((item for item in self._snapshot["requests"] if item.get("resourceId") == resource_id and item["status"] in {"pending", "supplementing", "summary-pending"}), None)
        if existing is not None:
            raise InvalidStateError(f"active request already exists for resource {resource_id}: {existing['id']}")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            request_id = self._new_request_id()
            task_id = self._delivery_task_id_for_request(request_id)
            query_text = query.strip() or self._ui_state.get("discoveryQuery") or DEFAULT_DISCOVERY_QUERY
            purpose = query_text or f"复用 {resource['name']}，仅补现场差异字段。"
            review_note = f"围绕 {resource['name']} 发起标准复用申请，待确认差异字段责任边界与回流要求。"
            request = {
                "id": request_id,
                "resourceId": resource_id,
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
            self._append_audit_feed("request.create", request_id, "ok", actor)
            return {"request_id": request_id, "status": request["status"]}

        return self._mutate("request.create", role, confirmed, {"resource_id": resource_id, "query": query}, mutation)

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

    def review_request(self, request_id: str, decision: str, role: str, confirmed: bool) -> dict[str, Any]:
        if decision == "approve":
            return self._approve_request(request_id, role, confirmed)
        if decision == "return_for_fix":
            return self._return_request_for_fix(request_id, role, confirmed)
        if decision == "reject":
            return self._reject_request(request_id, role, confirmed)
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
        if request["status"] != "completed" or task["backflow"]["status"] == "已确认":
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

    def configure_package_exposure(self, package_id: str, mode: str, role: str, confirmed: bool) -> dict[str, Any]:
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
            self._append_audit_feed("package.configure-exposure", package_id, "ok", actor)
            return {"package_id": package_id, "exposure": next_exposure}

        return self._mutate("package.configure_exposure", role, confirmed, {"package_id": package_id, "mode": mode}, mutation)

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
        if action not in {"publish", "revise"}:
            raise BrainServiceError(f"unsupported catalog action: {action}")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            if action == "publish":
                catalog["status"] = "已发布"
                catalog["issue"] = f"已由 {actor} 完成目录发布确认"
                catalog["governanceLocked"] = True
                result = "published"
                event_type = "catalog.publish"
            else:
                catalog["issue"] = f"已由 {actor} 修正目录说明与默认复用入口文案"
                catalog["governanceLocked"] = True
                result = "revised"
                event_type = "catalog.revise"
            provider["aiGovernance"]["summary"] = "目录治理动作已落账，当前可继续推进资源状态和专区正式投影。"
            self._append_audit_feed(event_type, catalog_id, "ok", actor)
            return {"catalog_id": catalog_id, "status": catalog["status"], "result": result}

        return self._mutate("catalog.manage_entry", role, confirmed, {"catalog_id": catalog_id, "action": action}, mutation)

    def manage_resource_asset(self, resource_id: str, action: str, role: str, confirmed: bool) -> dict[str, Any]:
        provider = self._snapshot["provider"]
        resource = next((item for item in provider["resources"] if item["id"] == resource_id), None)
        if resource is None:
            raise NotFoundError(resource_id)
        if action not in {"publish", "suspend"}:
            raise BrainServiceError(f"unsupported resource action: {action}")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            if action == "publish":
                resource["status"] = "可共享"
                resource["governanceLocked"] = True
                result = "published"
                event_type = "resource.publish"
            else:
                resource["status"] = "暂停共享"
                resource["governanceLocked"] = True
                result = "suspended"
                event_type = "resource.suspend"
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

    def register_package_version(self, package_id: str, role: str, confirmed: bool) -> dict[str, Any]:
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
            self._append_audit_feed("package.register-version", package_id, "ok", actor)
            return {"package_id": package_id, "registered_version": item["registeredVersion"]}

        return self._mutate("package.register_version", role, confirmed, {"package_id": package_id}, mutation)

    def apply_package_tenant_policy(self, package_id: str, role: str, confirmed: bool) -> dict[str, Any]:
        item = self._package_by_id(package_id)
        if item.get("versionStatus") != "registered":
            raise InvalidStateError("package version must be registered before tenant policy activation")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            item["tenantPolicy"] = {
                "tenantId": "default",
                "policyStatus": "enabled",
                "policy": {
                    "enabled": True,
                    "exposedSurfaces": item.get("exposure", []),
                    "requiresHuman": item.get("requiresHuman", False),
                    "auditClass": item.get("auditClass"),
                },
            }
            item["status"] = "approved"
            item["aiReview"]["summary"] = "租户策略已生效，能力包进入可控暴露状态；正式责任写动作仍然回到平台内建能力。"
            item["aiReview"]["draft"] = "策略结论：default 租户已启用该能力包，暴露面与审计级别沿用已审核结果。"
            self._append_audit_feed("package.apply-tenant-policy", package_id, "ok", actor)
            return {"package_id": package_id, "tenant_policy_status": item["tenantPolicy"]["policyStatus"]}

        return self._mutate("package.apply_tenant_policy", role, confirmed, {"package_id": package_id}, mutation)

    def review_package(self, package_id: str, decision: str, role: str, confirmed: bool) -> dict[str, Any]:
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

        return self._mutate("package.review_decide", role, confirmed, {"package_id": package_id, "decision": decision}, mutation)

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

    def _approve_request(self, request_id: str, role: str, confirmed: bool) -> dict[str, Any]:
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

        return self._mutate("approval.review_decide", role, confirmed, {"request_id": request_id, "decision": "approve"}, mutation)

    def _return_request_for_fix(self, request_id: str, role: str, confirmed: bool) -> dict[str, Any]:
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

        return self._mutate("approval.review_decide", role, confirmed, {"request_id": request_id, "decision": "return_for_fix"}, mutation)

    def _reject_request(self, request_id: str, role: str, confirmed: bool) -> dict[str, Any]:
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

        return self._mutate("approval.review_decide", role, confirmed, {"request_id": request_id, "decision": "reject"}, mutation)

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

    def _mutate(self, skill_id: str, role: str, confirmed: bool, payload: dict[str, Any], mutation: Any) -> dict[str, Any]:
        manifest = get_manifest(skill_id)
        if manifest.get("human_confirmation_required") and not confirmed:
            raise ConfirmationRequiredError(skill_id)
        actor = self._actor_for_role(role)
        audit_id = self._new_audit_id()
        self._emit_audit(audit_id, actor, skill_id, "before", payload)
        result = mutation(audit_id, actor)
        self._sync_state_views()
        self._persist()
        self._emit_audit(audit_id, actor, skill_id, "after", result)
        if manifest.get("side_effects"):
            self._sync_database_aggregates()
            self._enqueue_anchor(audit_id, actor, skill_id, payload | result)
        return {"ok": True, "skill_id": skill_id, "audit_id": audit_id, "result": result}

    def _persist(self) -> None:
        self._state_store.save(self._snapshot, self._ui_state)

    def _emit_audit(self, request_id: str, actor: str, skill_id: str, phase: str, payload: dict[str, Any]) -> None:
        audit_bus.emit(
            audit_bus.AuditEvent(
                request_id=request_id,
                actor=actor,
                skill_id=skill_id,
                phase=phase,
                payload=copy.deepcopy(payload),
            )
        )

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
            "service_id",
            "zone_id",
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
