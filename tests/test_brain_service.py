from __future__ import annotations

import asyncio
import base64
import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from zw_brain.command.brain import (
    AccessDeniedError,
    BrainService,
    BrainServiceError,
    ConfirmationRequiredError,
    InvalidStateError,
    InvalidTokenError,
)
from zw_brain.shared import audit as audit_bus
from zw_brain.shared.audit import AuditWriteError
from zw_brain.shared.audit import drain as drain_audit
from zw_brain.shared.queue import drain as drain_queue
from zw_brain.shared.state_store import StateStore


def make_service() -> tuple[TemporaryDirectory[str], BrainService]:
    tmp = TemporaryDirectory()
    audit_bus.configure_sink(lambda request_id, actor, skill_id, phase, payload: None)
    store = StateStore(Path(tmp.name) / "brain_state.json")
    return tmp, BrainService(state_store=store)


def make_database_service() -> tuple[TemporaryDirectory[str], BrainService]:
    import os

    tmp = TemporaryDirectory()
    os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp.name) / "zw_brain.db")

    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.migrate import ensure_runtime_schema

    ensure_runtime_schema()
    database_store = DatabaseStore()
    audit_bus.configure_sink(database_store.append_audit_event)
    return tmp, BrainService(state_store=StateStore(database_store=database_store))


def _encode_mock_jwt(payload: dict[str, object]) -> str:
    def _b64(data: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode("utf-8")).decode("utf-8").rstrip("=")

    header = _b64({"alg": "none", "typ": "JWT"})
    body = _b64(payload)
    return f"{header}.{body}.sig"


def test_requires_confirmation_for_write_skill() -> None:
    tmp, service = make_service()
    try:
        try:
            service.invoke_skill("approval.review_decide", {"request_id": "REQ-2026-04-25-0011", "decision": "approve"})
        except ConfirmationRequiredError:
            pass
        else:
            raise AssertionError("write skill must require explicit confirmation")
    finally:
        tmp.cleanup()


def test_write_skill_rejects_unauthorized_role() -> None:
    tmp, service = make_service()
    try:
        try:
            service.invoke_skill(
                "approval.review_decide",
                {"request_id": "REQ-2026-04-25-0011", "decision": "approve", "role": "r1", "confirmed": True},
            )
        except AccessDeniedError:
            pass
        else:
            raise AssertionError("unauthorized role must be rejected")
    finally:
        tmp.cleanup()


def test_tenant_scoped_skill_rejects_cross_tenant_payload() -> None:
    tmp, service = make_service()
    try:
        try:
            service.invoke_skill(
                "request.create",
                {"resource_id": "res-market-activity", "role": "r1", "tenant_id": "external", "confirmed": True},
            )
        except AccessDeniedError:
            pass
        else:
            raise AssertionError("cross-tenant invocation must be rejected")
    finally:
        tmp.cleanup()


def test_create_request_from_resource_enters_controlled_admission() -> None:
    tmp, service = make_service()
    try:
        drain_audit()
        asyncio.run(drain_queue())

        result = service.invoke_skill(
            "request.create",
            {
                "resource_id": "res-market-activity",
                "query": "我要为本周营商环境专题复用市场主体活跃度月度汇总，并进入受控准入。",
                "role": "r1",
                "confirmed": True,
            },
        )

        assert result["ok"] is True
        request_id = result["result"]["request_id"]
        snapshot = service.snapshot()
        request = next(item for item in snapshot["requests"] if item["id"] == request_id)
        approval = next(item for item in snapshot["approvals"] if item["id"] == request_id)
        delivery = next(item for item in snapshot["delivery_tasks"] if item["requestId"] == request_id)
        assert request["status"] == "pending"
        assert request["resourceId"] == "res-market-activity"
        assert approval["id"] == request_id
        assert delivery["id"] == request_id.replace("REQ-", "DLV-", 1)
        assert any(todo["id"] == request_id for todo in snapshot["workbench"]["r1"]["todos"])
        events = drain_audit()
        assert any(event.skill_id == "request.create" and event.phase == "before" for event in events)
        assert any(event.skill_id == "request.create" and event.phase == "after" for event in events)
        jobs = asyncio.run(drain_queue())
        assert jobs and jobs[0].topic == "blockchain.anchor"
    finally:
        tmp.cleanup()


def test_create_request_rejects_duplicate_active_resource_request() -> None:
    tmp, service = make_service()
    try:
        try:
            service.invoke_skill(
                "request.create",
                {"resource_id": "res-jbxx-ledger", "role": "r1", "confirmed": True},
            )
        except InvalidStateError:
            pass
        else:
            raise AssertionError("duplicate active resource request must be blocked")
    finally:
        tmp.cleanup()


def test_approve_request_updates_state_and_enqueues_anchor() -> None:
    tmp, service = make_service()
    try:
        drain_audit()
        asyncio.run(drain_queue())

        result = service.invoke_skill(
            "approval.review_decide",
            {"request_id": "REQ-2026-04-25-0011", "decision": "approve", "role": "r2", "confirmed": True},
        )

        assert result["ok"] is True
        snapshot = service.snapshot()
        request = next(item for item in snapshot["requests"] if item["id"] == "REQ-2026-04-25-0011")
        delivery = next(item for item in snapshot["delivery_tasks"] if item["requestId"] == "REQ-2026-04-25-0011")
        assert request["status"] == "supplementing"
        assert delivery["status"] == "supplementing"
        events = drain_audit()
        assert any(event.skill_id == "approval.review_decide" and event.phase == "before" for event in events)
        assert any(event.skill_id == "approval.review_decide" and event.phase == "after" for event in events)
        jobs = asyncio.run(drain_queue())
        assert jobs and jobs[0].topic == "blockchain.anchor"
    finally:
        tmp.cleanup()


def test_resubmit_request_restores_pending_state() -> None:
    tmp, service = make_service()
    try:
        result = service.invoke_skill(
            "request.submit",
            {"request_id": "REQ-2026-04-24-0007", "role": "r1", "confirmed": True},
        )

        assert result["ok"] is True
        snapshot = service.snapshot()
        request = next(item for item in snapshot["requests"] if item["id"] == "REQ-2026-04-24-0007")
        delivery = next(item for item in snapshot["delivery_tasks"] if item["requestId"] == "REQ-2026-04-24-0007")
        assert request["status"] == "pending"
        assert delivery["status"] == "warning"
        assert any(step["label"] == "已补齐后重新提交" for step in request["timeline"])
    finally:
        tmp.cleanup()


def test_delivery_receipt_reconcile_and_provider_service_toggle() -> None:
    tmp, service = make_service()
    try:
        reconcile = service.invoke_skill(
            "delivery.reconcile_receipt",
            {"task_id": "DLV-2026-04-25-0011", "role": "r6", "confirmed": True},
        )
        assert reconcile["ok"] is True

        suspend = service.invoke_skill(
            "service.publish_or_suspend",
            {"service_id": "svc-ledger-backflow", "action": "suspend", "role": "r6", "confirmed": True},
        )
        assert suspend["ok"] is True

        publish = service.invoke_skill(
            "service.publish_or_suspend",
            {"service_id": "svc-ledger-backflow", "action": "publish", "role": "r6", "confirmed": True},
        )
        assert publish["ok"] is True

        snapshot = service.snapshot()
        delivery = next(item for item in snapshot["delivery_tasks"] if item["id"] == "DLV-2026-04-25-0011")
        provider_service = next(item for item in snapshot["provider"]["services"] if item["id"] == "svc-ledger-backflow")
        assert delivery["receiptStatus"] == "reconciled"
        assert delivery["receiptNo"] == "RCPT-0011"
        assert provider_service["status"] == "在线"
    finally:
        tmp.cleanup()


def test_provider_publishing_controls_update_catalog_resource_and_zone() -> None:
    tmp, service = make_service()
    try:
        catalog = service.invoke_skill(
            "catalog.manage_entry",
            {"catalog_id": "cat-business", "action": "publish", "role": "r6", "confirmed": True},
        )
        assert catalog["ok"] is True

        resource = service.invoke_skill(
            "resource.manage_asset",
            {"resource_id": "res-company-visit", "action": "publish", "role": "r6", "confirmed": True},
        )
        assert resource["ok"] is True

        zone = service.invoke_skill(
            "zone.publish_topic_projection",
            {"zone_id": "business", "role": "r7", "confirmed": True},
        )
        assert zone["ok"] is True

        snapshot = service.snapshot()
        catalog_item = next(item for item in snapshot["provider"]["catalogs"] if item["id"] == "cat-business")
        resource_item = next(item for item in snapshot["provider"]["resources"] if item["id"] == "res-company-visit")
        zone_item = next(item for item in snapshot["zones"] if item["id"] == "business")
        assert catalog_item["status"] == "已发布"
        assert resource_item["status"] == "可共享"
        assert zone_item["status"] == "已发布"
    finally:
        tmp.cleanup()


def test_package_registry_actions_progress_from_approval_to_tenant_policy() -> None:
    tmp, service = make_service()
    try:
        approve = service.invoke_skill(
            "package.review_decide",
            {"package_id": "PKG-2026-04-25-001", "decision": "approve", "role": "r7", "confirmed": True},
        )
        assert approve["ok"] is True

        register = service.invoke_skill(
            "package.register_version",
            {"package_id": "PKG-2026-04-25-001", "role": "r7", "confirmed": True},
        )
        assert register["ok"] is True

        apply = service.invoke_skill(
            "package.apply_tenant_policy",
            {"package_id": "PKG-2026-04-25-001", "role": "r7", "confirmed": True},
        )
        assert apply["ok"] is True

        snapshot = service.snapshot()
        package = next(item for item in snapshot["capability_packages"] if item["id"] == "PKG-2026-04-25-001")
        assert package["status"] == "approved"
        assert package["versionStatus"] == "registered"
        assert package["registeredVersion"] == "v1.0.0"
        assert package["tenantPolicy"]["policyStatus"] == "enabled"
    finally:
        tmp.cleanup()


def test_delivery_recovery_and_package_exposure_configuration() -> None:
    tmp, service = make_service()
    try:
        recovery = service.invoke_skill(
            "delivery.trigger_recovery",
            {"task_id": "DLV-2026-04-23-0004", "role": "r6", "confirmed": True},
        )
        assert recovery["ok"] is True

        service.invoke_skill(
            "package.review_decide",
            {"package_id": "PKG-2026-04-25-001", "decision": "approve", "role": "r7", "confirmed": True},
        )
        service.invoke_skill(
            "package.register_version",
            {"package_id": "PKG-2026-04-25-001", "role": "r7", "confirmed": True},
        )
        exposure = service.invoke_skill(
            "package.configure_exposure",
            {"package_id": "PKG-2026-04-25-001", "mode": "expand", "role": "r7", "confirmed": True},
        )
        assert exposure["ok"] is True

        snapshot = service.snapshot()
        failed_delivery = next(item for item in snapshot["delivery_tasks"] if item["id"] == "DLV-2026-04-23-0004")
        package = next(item for item in snapshot["capability_packages"] if item["id"] == "PKG-2026-04-25-001")
        assert failed_delivery["status"] == "warning"
        assert any(step["state"] == "恢复已触发" for step in failed_delivery["history"])
        assert "a2a" in package["exposure"]
        assert "a2a" in package["compatibility"]
    finally:
        tmp.cleanup()


def test_dispute_investigation_and_escalation_update_timeline_and_owner() -> None:
    tmp, service = make_service()
    try:
        progress = service.invoke_skill(
            "compliance.investigate_case",
            {"dispute_id": "DSP-2026-04-25-0003", "action": "progress", "role": "r8", "confirmed": True},
        )
        assert progress["ok"] is True

        escalate = service.invoke_skill(
            "compliance.investigate_case",
            {"dispute_id": "DSP-2026-04-25-0003", "action": "escalate", "role": "r8", "confirmed": True},
        )
        assert escalate["ok"] is True

        snapshot = service.snapshot()
        dispute = next(item for item in snapshot["disputes"] if item["id"] == "DSP-2026-04-25-0003")
        assert dispute["status"] == "escalated"
        assert dispute["owner"] == "区台账治理组"
        assert any(step["label"] == "推进调查" for step in dispute["timeline"])
        assert any(step["label"] == "升级治理" for step in dispute["timeline"])
    finally:
        tmp.cleanup()


def test_ambiguous_legacy_mapping_raises_without_canonical_resource_id() -> None:
    """When multiple discovery.resources share the same legacy code, submit must not pick arbitrarily."""
    import copy as copy_mod

    tmp, service = make_database_service()
    try:
        base = next(r for r in service._snapshot["discovery"]["resources"] if r["id"] == "res-jbxx-ledger")
        dup = copy_mod.deepcopy(base)
        dup["id"] = "res-legacy-shadow-dup"
        service._snapshot["discovery"]["resources"].append(dup)
        service._snapshot["provider"]["catalogs"].append(
            {
                "id": "cat-ambiguous-no-canonical",
                "name": "Ambiguous catalog (test fixture)",
                "legacy_object_ref": "370000308004000000/000001",
            }
        )
        try:
            service.invoke_skill(
                "application.resource.submit",
                {"resource_id": "cat-ambiguous-no-canonical", "role": "r1", "confirmed": True},
            )
        except BrainServiceError as exc:
            assert "ambiguous" in str(exc).lower()
        else:
            raise AssertionError("expected BrainServiceError when legacy matches multiple resources without canonical_resource_id")
    finally:
        tmp.cleanup()


def test_application_resource_submit_resolves_provider_catalog_alias() -> None:
    """Default discovery surfaces catalog codes (cat-parking); submit resolves to canonical template id."""
    tmp, service = make_database_service()
    try:
        try:
            service.invoke_skill(
                "application.resource.submit",
                {"resource_id": "cat-parking", "role": "r1", "confirmed": True},
            )
        except InvalidStateError as exc:
            assert "res-jbxx-ledger" in str(exc)
        else:
            raise AssertionError("expected duplicate guard once alias maps to res-jbxx-ledger")
        snap = service.snapshot()
        assert snap["webui"]["dashboardHref"] == "/dashboard/"
    finally:
        tmp.cleanup()



def test_formal_governance_capability_aliases_use_canonical_paths() -> None:
    tmp, service = make_database_service()
    try:
        package = service.invoke_skill(
            "capability.package.register",
            {
                "slug": "sample.formal.capability",
                "package_id": "PKG-FORMAL-001",
                "source": "zw-brain registry",
                "description": "只读辅助能力",
                "role": "r7",
                "confirmed": True,
            },
        )
        assert package["ok"] is True

        approve = service.invoke_skill(
            "capability.version.review",
            {"package_id": "PKG-FORMAL-001", "decision": "approve", "role": "r7", "confirmed": True},
        )
        assert approve["ok"] is True

        register = service.invoke_skill(
            "capability.version.submit",
            {"package_id": "PKG-FORMAL-001", "role": "r7", "confirmed": True},
        )
        assert register["ok"] is True

        exposure = service.invoke_skill(
            "capability.exposure.configure",
            {"package_id": "PKG-FORMAL-001", "mode": "expand", "role": "r7", "confirmed": True},
        )
        assert exposure["ok"] is True

        enabled = service.invoke_skill(
            "tenant.capability.enable",
            {"package_id": "PKG-FORMAL-001", "role": "r7", "confirmed": True},
        )
        assert enabled["ok"] is True

        disabled = service.invoke_skill(
            "tenant.capability.disable",
            {"package_id": "PKG-FORMAL-001", "role": "r7", "confirmed": True},
        )
        assert disabled["ok"] is True

        created = service.invoke_skill(
            "catalog.entry.create",
            {"catalog_code": "cat-formal-001", "title": "正式目录", "role": "r6", "confirmed": True},
        )
        assert created["ok"] is True

        updated = service.invoke_skill(
            "catalog.entry.update",
            {"catalog_code": "cat-formal-001", "title": "正式目录修订", "role": "r6", "confirmed": True},
        )
        assert updated["ok"] is True

        exported = service.invoke_skill("registry.artifact.export", {"role": "r7"})
        assert exported["total"] >= 1

        snapshot = service.snapshot()
        item = next(entry for entry in snapshot["capability_packages"] if entry["id"] == "PKG-FORMAL-001")
        assert item["status"] == "approved"
        assert item["versionStatus"] == "registered"
        assert item["tenantPolicy"]["policyStatus"] == "disabled"
    finally:
        tmp.cleanup()


def test_compliance_p6_minimal_closure_and_adapter_receipts() -> None:
    tmp, service = make_database_service()
    try:
        signal = service.invoke_skill(
            "compliance.signal.ingest",
            {"adapter_slug": "compliance-center", "source_ref": "sig-001", "role": "r8", "confirmed": True},
        )
        assert signal["ok"] is True

        security = service.invoke_skill(
            "security.scan.result.sync",
            {"adapter_slug": "security-center", "source_ref": "scan-001", "role": "r8", "confirmed": True},
        )
        assert security["ok"] is True

        standard = service.invoke_skill(
            "standard.asset.recommend",
            {"adapter_slug": "standard-service", "source_ref": "std-001", "role": "r8", "confirmed": True},
        )
        assert standard["ok"] is True

        rule = service.invoke_skill(
            "compliance.rule.configure",
            {"rule_id": "rule-001", "title": "重复采集合规规则", "role": "r8", "confirmed": True},
        )
        assert rule["ok"] is True

        opened = service.invoke_skill(
            "compliance.case.open",
            {"case_id": "CMP-001", "title": "重复采集风险", "severity": "high", "role": "r8", "confirmed": True},
        )
        assert opened["ok"] is True
        assert opened["result"]["status"] == "detected"

        assigned = service.invoke_skill(
            "compliance.case.assign",
            {"case_id": "CMP-001", "owner": "区减负治理组", "role": "r8", "confirmed": True},
        )
        assert assigned["result"]["status"] == "assigned"

        resolved = service.invoke_skill(
            "compliance.case.resolve",
            {"case_id": "CMP-001", "summary": "已完成处置", "role": "r8", "confirmed": True},
        )
        assert resolved["result"]["status"] == "resolved"

        closed = service.invoke_skill(
            "compliance.case.close",
            {"case_id": "CMP-001", "role": "r8", "confirmed": True},
        )
        assert closed["result"]["status"] == "closed"

        cases = service.invoke_skill("compliance.case.query", {"status": "closed", "role": "r8"})
        metrics = service.invoke_skill("compliance.metric.query", {"role": "r8"})
        dashboard = service.invoke_skill("dashboard.compliance.query", {"role": "r8"})

        assert any(item["id"] == "CMP-001" for item in cases["items"])
        assert metrics["by_status"]["closed"] >= 1
        assert dashboard["summary"]["resolved_count"] >= 1
    finally:
        tmp.cleanup()


def test_full_golden_path_reaches_backflow_confirmed() -> None:
    tmp, service = make_service()
    try:
        service.invoke_skill("approval.review_decide", {"request_id": "REQ-2026-04-25-0011", "decision": "approve", "role": "r2", "confirmed": True})
        service.invoke_skill("supplement.submit", {"request_id": "REQ-2026-04-25-0011", "role": "r3", "confirmed": True})
        service.invoke_skill("summary.confirm", {"request_id": "REQ-2026-04-25-0011", "role": "r5", "confirmed": True})
        service.invoke_skill("delivery.reconcile_receipt", {"task_id": "DLV-2026-04-25-0011", "role": "r6", "confirmed": True})
        service.invoke_skill("backflow.confirm", {"task_id": "DLV-2026-04-25-0011", "role": "r6", "confirmed": True})

        snapshot = service.snapshot()
        request = next(item for item in snapshot["requests"] if item["id"] == "REQ-2026-04-25-0011")
        delivery = next(item for item in snapshot["delivery_tasks"] if item["id"] == "DLV-2026-04-25-0011")
        zone = next(item for item in snapshot["zones"] if item["id"] == "business")
        assert request["status"] == "completed"
        assert delivery["backflow"]["status"] == "已确认"
        assert "v1.3" in zone["trust"][1]
    finally:
        tmp.cleanup()


def test_generated_request_journey_reaches_backflow_confirmed() -> None:
    tmp, service = make_service()
    try:
        created = service.invoke_skill(
            "application.resource.submit",
            {"resource_id": "res-market-activity", "query": "市场主体活跃度", "role": "r1", "confirmed": True},
        )
        request_id = created["result"]["request_id"]
        task_id = request_id.replace("REQ-", "DLV-", 1)

        service.invoke_skill("application.resource.review", {"request_id": request_id, "decision": "approve", "role": "r2", "confirmed": True})
        service.invoke_skill("supplement.submit", {"request_id": request_id, "role": "r3", "confirmed": True})
        service.invoke_skill("summary.confirm", {"request_id": request_id, "role": "r5", "confirmed": True})
        service.invoke_skill("delivery.reconcile_receipt", {"task_id": task_id, "role": "r6", "confirmed": True})
        service.invoke_skill("backflow.confirm", {"task_id": task_id, "role": "r6", "confirmed": True})

        snapshot = service.snapshot()
        request = next(item for item in snapshot["requests"] if item["id"] == request_id)
        delivery = next(item for item in snapshot["delivery_tasks"] if item["id"] == task_id)
        assert request["status"] == "completed"
        assert delivery["status"] == "completed"
        assert delivery["backflow"]["status"] == "已确认"
        assert any(item["type"] == "backflow.confirm" for item in snapshot["audit_events"])
    finally:
        tmp.cleanup()


def test_backflow_confirm_requires_reconciled_receipt() -> None:
    tmp, service = make_service()
    try:
        service.invoke_skill("approval.review_decide", {"request_id": "REQ-2026-04-25-0011", "decision": "approve", "role": "r2", "confirmed": True})
        service.invoke_skill("supplement.submit", {"request_id": "REQ-2026-04-25-0011", "role": "r3", "confirmed": True})
        service.invoke_skill("summary.confirm", {"request_id": "REQ-2026-04-25-0011", "role": "r5", "confirmed": True})

        try:
            service.invoke_skill("backflow.confirm", {"task_id": "DLV-2026-04-25-0011", "role": "r6", "confirmed": True})
        except InvalidStateError:
            pass
        else:
            raise AssertionError("backflow.confirm must require a reconciled receipt")
    finally:
        tmp.cleanup()


def test_delivery_exchange_records_execution_without_overwriting_canonical_delivery_status() -> None:
    tmp, service = make_database_service()
    try:
        service.invoke_skill(
            "approval.review_decide",
            {"request_id": "REQ-2026-04-25-0011", "decision": "approve", "role": "r2", "confirmed": True},
        )
        service.invoke_skill("delivery.access.grant", {"task_id": "DLV-2026-04-25-0011", "role": "r6", "confirmed": True})
        before = service.invoke_skill("delivery.view", {"task_id": "DLV-2026-04-25-0011", "role": "r6"})["status"]

        stopped = service.invoke_skill(
            "delivery.exchange.stop",
            {"task_id": "DLV-2026-04-25-0011", "role": "r6", "confirmed": True, "reason": "executor paused"},
        )
        after = service.invoke_skill("delivery.view", {"task_id": "DLV-2026-04-25-0011", "role": "r6"})["status"]

        assert stopped["result"]["state"] == "stopped"
        assert before == "completed"
        assert after == "completed"
        store = service._state_store.database_store
        assert store is not None
        attempts = store.delivery_repo.list_attempts(delivery_code="DLV-2026-04-25-0011")
        evidence = store.delivery_repo.list_execution_evidence(delivery_code="DLV-2026-04-25-0011")
        metrics = store.delivery_repo.list_exchange_metrics(delivery_code="DLV-2026-04-25-0011")
        assert any(item.state == "stopped" for item in attempts)
        assert any(item.result_status == "stopped" for item in evidence)
        assert any(item.failed_count == 1 for item in metrics)
    finally:
        tmp.cleanup()

def test_audit_payloads_are_sanitized_and_failed_calls_are_recorded() -> None:
    tmp, service = make_database_service()
    try:
        try:
            service.invoke_skill(
                "compliance.case.open",
                {"case_id": "DSP-2026-04-25-0003", "title": "duplicate", "role": "r8", "confirmed": True, "password": "drop-me"},
            )
        except Exception:
            pass
        else:
            raise AssertionError("missing resource should fail")

        store = service._state_store.database_store
        assert store is not None
        audit_payloads = [event.payload_json for event in store.list_audit_events() if event.skill_id == "compliance.case.open"]
        assert audit_payloads
        assert all("password" not in payload for payload in audit_payloads)
        failed_calls = [item for item in store.list_capability_calls() if item.skill_id == "compliance.case.open" and item.status == "failed"]
        assert failed_calls
        assert "password" not in failed_calls[0].input_json
    finally:
        tmp.cleanup()


def test_gateway_heartbeat_ingest_is_idempotent_with_database() -> None:
    with TemporaryDirectory() as tmp:
        import os

        db_path = Path(tmp) / "zw_brain.db"
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))

        service.invoke_skill(
            "ops.gateway.heartbeat.ingest",
            {
                "gateway_instance_id": "gw-api-main",
                "runtime_profile": "active-active",
                "status": "online",
                "role": "r6",
                "confirmed": True,
            },
        )
        service.invoke_skill(
            "ops.gateway.heartbeat.ingest",
            {
                "gateway_instance_id": "gw-api-main",
                "gateway_address_ref": "gw-ref-main",
                "status": "warning",
                "role": "r6",
                "confirmed": True,
            },
        )

        report = service.invoke_skill("ops.service.report.query", {"role": "r6"})
        assert report["summary"]["gatewayCount"] == 1
        assert report["gateways"][0]["status"] == "warning"
        assert report["gateways"][0]["runtime_profile"] == "active-active"
        assert any(item.skill_id == "ops.gateway.heartbeat.ingest" for item in database_store.list_audit_events())


def test_service_invocation_query_reads_projection_metrics() -> None:
    with TemporaryDirectory() as tmp:
        import os

        db_path = Path(tmp) / "zw_brain.db"
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        service = BrainService(state_store=StateStore(database_store=database_store))
        database_store.service_invocation_repo.upsert_metric(
            {
                "metric_scope": "resource",
                "resource_code": "api-custom-ledger",
                "provider_org_id": "org-provider",
                "consumer_org_id": "org-consumer",
                "time_bucket": "2026-04-29",
                "invoke_count": 42,
                "success_count": 40,
                "failed_count": 2,
                "error_count": 1,
                "avg_latency_ms": 83,
                "source_event_ref": "metric-ref-1",
            }
        )

        result = service.invoke_skill("ops.service.invocation.query", {"resource_code": "api-custom-ledger", "role": "r6"})

        assert result["summary"]["invokeCount"] == 42
        assert result["summary"]["failedCount"] == 2
        assert result["items"][0]["failed_count"] == 2
        assert result["items"][0]["source_event_ref"] == "metric-ref-1"


def test_api_resource_lifecycle_and_policy_filter_sensitive_fields() -> None:
    tmp, service = make_service()
    try:
        registered = service.invoke_skill(
            "resource.api.register",
            {
                "resource_code": "api-company-ledger",
                "title": "法人单位基础信息 API",
                "owner_org_id": "org-market-regulator",
                "catalog_code": "cat-api-company-ledger",
                "summary_json": {"domain": "法人基础信息", "nested": {"token": "should-not-persist"}, "secret": "should-not-persist"},
                "channel_binding": {
                    "binding_code": "bind-company-ledger",
                    "route_ref": "route-ref-company-ledger",
                    "auth_ref": "auth-ref-company-ledger",
                    "gateway_policy_json": {"rate_limit": "1000/m", "nested": {"secret": "should-not-persist"}, "token": "should-not-persist"},
                },
                "role": "r6",
                "confirmed": True,
            },
        )
        assert registered["result"]["lifecycle_status"] == "draft"
        assert "secret" not in registered["result"]["summary_json"]
        assert registered["result"]["summary_json"]["nested"] == {}

        service.invoke_skill("resource.api.submit_review", {"resource_code": "api-company-ledger", "role": "r6", "confirmed": True})
        service.invoke_skill(
            "resource.api.review",
            {"resource_code": "api-company-ledger", "decision": "approve", "role": "r7", "confirmed": True},
        )
        active = service.invoke_skill("resource.api.publish", {"resource_code": "api-company-ledger", "role": "r7", "confirmed": True})
        assert active["result"]["lifecycle_status"] == "active"

        policy_update = service.invoke_skill(
            "resource.api.policy.update",
            {
                "resource_code": "api-company-ledger",
                "binding_code": "bind-company-ledger",
                "gateway_policy_json": {"rate_limit": "800/m", "rules": [{"name": "daily", "password": "should-not-persist"}]},
                "role": "r6",
                "confirmed": True,
            },
        )
        assert policy_update["result"]["gateway_policy_json"] == {"rate_limit": "800/m", "rules": [{"name": "daily"}]}
        assert service.invoke_skill("data.search", {"query": "法人单位基础信息 API", "role": "r6"})["total"] >= 1
    finally:
        tmp.cleanup()



def test_api_resource_lifecycle_updates_approval_case_with_database() -> None:
    with TemporaryDirectory() as tmp:
        import os

        db_path = Path(tmp) / "zw_brain.db"
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))

        service.invoke_skill(
            "resource.api.register",
            {
                "resource_code": "api-approval-ledger",
                "title": "审批 API",
                "source_ref": "dsp-dataservice:api_service_info",
                "role": "r6",
                "confirmed": True,
            },
        )
        service.invoke_skill("resource.api.submit_review", {"resource_code": "api-approval-ledger", "role": "r6", "confirmed": True})
        service.invoke_skill(
            "resource.api.review",
            {"resource_code": "api-approval-ledger", "decision": "approve", "role": "r7", "confirmed": True},
        )
        service.invoke_skill("resource.api.publish", {"resource_code": "api-approval-ledger", "role": "r7", "confirmed": True})

        cases = [item for item in database_store.approval_repo.list_cases() if item.application_code == "api-approval-ledger"]
        assert len(cases) == 1
        assert cases[0].decision_payload_json["status"] == "active"
        steps = database_store.approval_repo.list_steps("api-approval-ledger")
        decisions = database_store.approval_repo.list_decisions("api-approval-ledger")
        assert [step.step_name for step in steps] == [
            "API 服务资源审核",
            "API 服务资源审核通过",
            "API 服务资源发布",
        ]
        assert [decision.decision for decision in decisions] == ["submit", "approve", "approve"]



def test_catalog_metadata_capabilities_write_sanitized_evidence_with_database() -> None:
    with TemporaryDirectory() as tmp:
        import os

        db_path = Path(tmp) / "zw_brain.db"
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))

        model = service.invoke_skill(
            "catalog.model.upsert",
            {
                "model_code": "legal-person-base",
                "title": "法人单位基础信息模板",
                "status": "active",
                "model_schema_json": {"fields": ["credit_code"], "secret": "should-not-persist"},
                "fields": [
                    {
                        "field_code": "credit_code",
                        "title": "统一社会信用代码",
                        "field_policy_json": {"share_condition": "审批后共享", "token": "should-not-persist"},
                    }
                ],
                "source_ref": "dsp-catalog3:model_catalog_template:tpl-1",
                "role": "r6",
                "confirmed": True,
            },
        )
        assert model["result"]["model_code"] == "legal-person-base"

        snapshot = service.invoke_skill(
            "metadata.schema.snapshot.upsert",
            {
                "snapshot_ref": "schema-res-1-v1",
                "resource_code": "res-legal-person",
                "binding_code": "bind-table-1",
                "schema_json": {"columns": ["credit_code"], "password": "should-not-persist"},
                "source_ref": "dsp-metadata3:gather:gather-1",
                "role": "r6",
                "confirmed": True,
            },
        )
        assert snapshot["result"]["snapshot_ref"] == "schema-res-1-v1"

        mapping = service.invoke_skill(
            "catalog.schema.mapping.upsert",
            {
                "mapping_code": "map-credit-code",
                "catalog_code": "cat-legal-person",
                "catalog_item_code": "credit_code",
                "resource_code": "res-legal-person",
                "binding_code": "bind-table-1",
                "source_schema_ref": {"table": "t_legal_person", "column": "credit_code", "secret": "should-not-persist"},
                "mapping_rule_json": {"method": "direct", "token": "should-not-persist"},
                "evidence_ref": "schema-res-1-v1",
                "source_ref": "dsp-metadata3:rc_resource_catalog_item_link:link-1",
                "legacy_object_ref": "link-1",
                "role": "r6",
                "confirmed": True,
            },
        )
        assert mapping["result"]["mapping_code"] == "map-credit-code"

        gather = service.invoke_skill(
            "metadata.gather.evidence.upsert",
            {
                "gather_task_ref": "gather-1",
                "resource_code": "res-legal-person",
                "source_system_ref": "dsp-metadata3:meta_gather_task:gather-1",
                "schema_snapshot_ref": "schema-res-1-v1",
                "status": "succeeded",
                "evidence_json": {"rows": 2, "secret": "should-not-persist"},
                "role": "r6",
                "confirmed": True,
            },
        )
        assert gather["result"]["status"] == "succeeded"

        lineage = service.invoke_skill(
            "metadata.lineage.upsert",
            {
                "relation_ref": "lineage-1",
                "relation_scope": "column",
                "source_resource_code": "res-source",
                "source_schema_ref": "source.credit_code",
                "target_resource_code": "res-legal-person",
                "target_schema_ref": "target.credit_code",
                "source_evidence_ref": "dsp-metadata3:lineage:lineage-1",
                "relation_rule_json": {"expr": "direct", "secret": "should-not-persist"},
                "role": "r8",
                "confirmed": True,
            },
        )
        assert lineage["result"]["relation_ref"] == "lineage-1"

        quality = service.invoke_skill(
            "ops.catalog.quality.upsert",
            {
                "quality_ref": "quality-1",
                "target_type": "catalog_item",
                "target_ref": "credit_code",
                "quality_status": "passed",
                "score": 96,
                "evidence_json": {"missing": 0, "secret": "should-not-persist"},
                "source_ref": "dsp-monitor:quality:quality-1",
                "role": "r8",
                "confirmed": True,
            },
        )
        assert quality["result"]["quality_status"] == "passed"

        assert database_store.catalog_repo.list_models()[0].model_schema_json == {"fields": ["credit_code"]}
        assert database_store.catalog_repo.list_model_fields("legal-person-base")[0].field_policy_json == {"share_condition": "审批后共享"}
        schema_mapping = database_store.metadata_evidence_repo.list_schema_mappings(resource_code="res-legal-person")[0]
        assert schema_mapping.source_schema_ref == {"table": "t_legal_person", "column": "credit_code"}
        assert any(item.skill_id == "catalog.schema.mapping.upsert" for item in database_store.list_audit_events())
        assert any(item.legacy_object_ref == "link-1" for item in database_store.legacy_mapping_repo.list_mappings(canonical_type="resource_schema_mapping"))

        assert service.invoke_skill("catalog.model.query", {"model_code": "legal-person-base", "role": "r6"})["total"] == 1
        assert service.invoke_skill("catalog.model.field.query", {"model_code": "legal-person-base", "role": "r6"})["items"][0]["field_policy_json"] == {"share_condition": "审批后共享"}
        schema_projection = service.invoke_skill("metadata.schema.query", {"resource_code": "res-legal-person", "role": "r6"})["items"][0]
        assert schema_projection["schema_json"] == {"columns": ["credit_code"]}
        assert schema_projection["source_ref"] == "dsp-metadata3:gather:gather-1"
        assert schema_projection["captured_at"]
        catalog_item_projection = service.invoke_skill("metadata.catalog_item.query", {"resource_code": "res-legal-person", "role": "r6"})["items"][0]
        assert catalog_item_projection["source_schema_ref"] == {"table": "t_legal_person", "column": "credit_code"}
        assert catalog_item_projection["source_ref"] == "schema-res-1-v1"
        assert catalog_item_projection["generated_at"]
        gather_projection = service.invoke_skill("metadata.gather.evidence.query", {"resource_code": "res-legal-person", "role": "r6"})["items"][0]
        assert gather_projection["source_ref"] == "dsp-metadata3:meta_gather_task:gather-1"
        assert gather_projection["generated_at"]
        assert gather_projection["projection_only"] is True
        lineage_projection = service.invoke_skill("metadata.lineage.query", {"resource_code": "res-legal-person", "role": "r8"})
        assert lineage_projection["total"] == 1
        assert lineage_projection["items"][0]["source_ref"] == "dsp-metadata3:lineage:lineage-1"
        assert lineage_projection["items"][0]["generated_at"]
        quality_projection = service.invoke_skill("ops.catalog.quality.query", {"target_ref": "credit_code", "role": "r8"})["items"][0]
        assert quality_projection["evidence_json"] == {"missing": 0}
        assert quality_projection["source_ref"] == "dsp-monitor:quality:quality-1"
        assert quality_projection["generated_at"]
        statistics = service.invoke_skill("ops.catalog.statistics.query", {"role": "r8"})["summary"]
        assert statistics["schemaMappingCount"] == 1
        assert statistics["qualityEvidenceCount"] == 1
        assert statistics["source_ref"] == "canonical_projection"
        assert statistics["generated_at"]
        assert statistics["projection_only"] is True



def test_reconstruction_core_capability_names_cover_catalog_resource_application_delivery() -> None:
    with TemporaryDirectory() as tmp:
        import os

        db_path = Path(tmp) / "zw_brain.db"
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))

        draft = service.invoke_skill(
            "catalog.entry.create_draft",
            {
                "catalog_code": "cat-core-demo",
                "title": "核心目录草稿",
                "owner_org_id": "区政数局",
                "region_code": "370100",
                "summary_json": {"domain": "法人", "secret": "should-not-persist"},
                "items": [
                    {
                        "item_code": "credit_code",
                        "title": "统一社会信用代码",
                        "resource_code": "api-core-demo",
                        "summary_json": {"token": "should-not-persist"},
                    }
                ],
                "role": "r6",
                "confirmed": True,
            },
        )
        assert draft["result"]["lifecycle_status"] == "draft"
        service.invoke_skill("catalog.entry.submit_review", {"catalog_code": "cat-core-demo", "role": "r6", "confirmed": True})
        reviewed = service.invoke_skill("catalog.entry.review", {"catalog_code": "cat-core-demo", "decision": "approve", "role": "r7", "confirmed": True})
        assert reviewed["result"]["lifecycle_status"] == "approved_pending_publish"
        published = service.invoke_skill("catalog.entry.publish", {"catalog_code": "cat-core-demo", "role": "r7", "confirmed": True})
        assert published["result"]["lifecycle_status"] == "active"
        summary = service.invoke_skill("catalog.entry.query", {"catalog_code": "cat-core-demo", "role": "r6"})["items"][0]["summary_json"]
        assert summary["summary_json"]["domain"] == "法人"
        assert "secret" not in summary["summary_json"]

        service.invoke_skill(
            "resource.api.register",
            {
                "resource_code": "api-core-demo",
                "title": "核心资源 API",
                "catalog_code": "cat-core-demo",
                "role": "r6",
                "confirmed": True,
            },
        )
        service.invoke_skill("resource.asset.submit_review", {"resource_code": "api-core-demo", "role": "r6", "confirmed": True})
        reviewed_resource = service.invoke_skill("resource.asset.review", {"resource_code": "api-core-demo", "decision": "approve", "role": "r7", "confirmed": True})
        assert reviewed_resource["result"]["lifecycle_status"] == "approved_pending_publish"
        resource = service.invoke_skill("resource.asset.publish", {"resource_code": "api-core-demo", "role": "r7", "confirmed": True})
        assert resource["result"]["lifecycle_status"] == "active"
        assert service.invoke_skill("resource.asset.query", {"resource_code": "api-core-demo", "role": "r6"})["total"] == 1

        bind = service.invoke_skill(
            "catalog.resource.bind",
            {
                "mapping_code": "bind-core-demo-credit-code",
                "catalog_code": "cat-core-demo",
                "catalog_item_code": "credit_code",
                "resource_code": "api-core-demo",
                "binding_code": "binding-core-demo",
                "source_schema_ref": {"column": "credit_code", "password": "should-not-persist"},
                "mapping_rule_json": {"method": "direct", "secret": "should-not-persist"},
                "role": "r6",
                "confirmed": True,
            },
        )
        assert bind["result"]["mapping_code"] == "bind-core-demo-credit-code"
        assert service.invoke_skill("metadata.catalog_item.query", {"catalog_code": "cat-core-demo", "role": "r6"})["items"][0]["source_schema_ref"] == {"column": "credit_code"}
        service.invoke_skill("catalog.entry.withdraw", {"catalog_code": "cat-core-demo", "role": "r7", "confirmed": True})
        withdrawn = service.invoke_skill("catalog.entry.query", {"catalog_code": "cat-core-demo", "role": "r6"})["items"][0]
        assert withdrawn["lifecycle_status"] == "retired"
        versions = database_store.catalog_repo.list_entry_versions("cat-core-demo")
        assert [item.version_status for item in versions] == ["active", "retired"]
        catalog_steps = database_store.approval_repo.list_steps("cat-core-demo")
        catalog_decisions = database_store.approval_repo.list_decisions("cat-core-demo")
        assert [item.step_name for item in catalog_steps] == [
            "目录资源审核",
            "目录资源审核通过",
            "目录资源发布",
            "目录资源撤回",
        ]
        assert [item.decision for item in catalog_decisions] == ["submit", "approve", "approve", "close"]

        request = service.invoke_skill(
            "application.resource.submit",
            {
                "resource_id": "res-market-activity",
                "query": "复用法人模板，只补现场差异字段。",
                "role": "r1",
                "confirmed": True,
            },
        )
        request_id = request["result"]["request_id"]
        service.invoke_skill("application.resource.review", {"request_id": request_id, "decision": "approve", "role": "r2", "confirmed": True})
        task_id = request_id.replace("REQ-", "DLV-", 1)
        grant = service.invoke_skill("delivery.access.grant", {"task_id": task_id, "role": "r6", "confirmed": True})
        assert grant["result"]["status"] == "completed"

        assert service.invoke_skill("catalog.group.query", {"role": "r6"})["total"] >= 1
        assert service.invoke_skill("catalog.share_zone.query", {"role": "r6"})["total"] >= 1
        audit_skill_ids = [item.skill_id for item in database_store.list_audit_events()]
        for skill_id in [
            "catalog.entry.withdraw",
            "resource.asset.submit_review",
            "resource.asset.review",
            "resource.asset.publish",
            "application.resource.submit",
            "application.resource.review",
            "delivery.access.grant",
        ]:
            assert skill_id in audit_skill_ids


def test_dsp_dataservice_objects_write_legacy_mappings() -> None:
    with TemporaryDirectory() as tmp:
        import os

        db_path = Path(tmp) / "zw_brain.db"
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))

        service.invoke_skill(
            "resource.api.register",
            {
                "resource_code": "api-trace-ledger",
                "title": "追溯 API",
                "source_ref": "dsp-dataservice:api_service_info",
                "channel_binding": {
                    "binding_code": "bind-trace-ledger",
                    "source_ref": "dsp-dataservice:api_service_proxy",
                },
                "role": "r6",
                "confirmed": True,
            },
        )
        service.invoke_skill(
            "ops.gateway.heartbeat.ingest",
            {
                "gateway_instance_id": "gw-trace",
                "source_ref": "dsp-dataservice:/openapi/report",
                "status": "online",
                "role": "r6",
                "confirmed": True,
            },
        )
        database_store.service_invocation_repo.upsert_metric(
            {
                "metric_scope": "resource",
                "resource_code": "api-trace-ledger",
                "provider_org_id": "org-provider",
                "consumer_org_id": "org-consumer",
                "time_bucket": "2026-04-29",
                "invoke_count": 9,
                "success_count": 8,
                "failure_count": 1,
                "source_event_ref": "dsp-dataservice:api_service_times",
            }
        )

        mappings = database_store.legacy_mapping_repo.list_mappings()
        canonical_types = {item.canonical_type for item in mappings}
        assert {
            "resource_asset",
            "resource_channel_binding",
            "gateway_runtime_status_projection",
            "service_invocation_metric_projection",
        }.issubset(canonical_types)
        dsp_mappings = [item for item in mappings if item.legacy_system == "dsp-dataservice"]
        assert dsp_mappings
        assert any(item.legacy_object_type == "api_service_info" for item in dsp_mappings)
        assert any(item.legacy_object_type == "/openapi/report" for item in dsp_mappings)


def test_service_projection_source_kind_and_external_packages() -> None:
    with TemporaryDirectory() as tmp:
        import os

        db_path = Path(tmp) / "zw_brain.db"
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        service = BrainService(state_store=StateStore(database_store=database_store))
        database_store.service_invocation_repo.upsert_metric(
            {
                "metric_scope": "resource",
                "resource_code": "api-source-kind",
                "time_bucket": "2026-04-29",
                "invoke_count": 3,
                "source_event_ref": "dsp-dataservice:gateway_log:20260429",
            }
        )

        metrics = service.invoke_skill("ops.service.invocation.query", {"resource_code": "api-source-kind", "role": "r6"})["items"]
        assert metrics[0]["summary_json"]["source_kind"] == "gateway_adapter"

        packages = {item["slug"]: item for item in service.invoke_skill("package.list", {"role": "r7"})["items"]}
        for slug in {
            "dsp.gateway.runtime.adapter",
            "dsp.environment.diagnostics.adapter",
            "dsp.ticket.cmdb.wiki.adapter",
            "dsp.wsdl.import.adapter",
            "dsp.orchestrator.http.dataservice.adapter",
        }:
            package = packages[slug]
            assert package["contract"]["inputs"]
            assert package["contract"]["outputs"]
            assert package["auditClass"]
            assert package["tenantPolicy"]["scope"] == "tenant-bound"
            assert package["tenantPolicy"]["writeCanonicalState"] is False
            assert package["failureWriteback"]["target"] == "audit_event"
            assert package["failureWriteback"]["mode"]
            assert package["runtimeBinding"]["protocol"]



def test_gateway_log_anchor_writes_sanitized_outbox_request() -> None:
    with TemporaryDirectory() as tmp:
        import os

        db_path = Path(tmp) / "zw_brain.db"
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))

        try:
            service.invoke_skill(
                "ops.gateway.log.anchor",
                {"gateway_log_ref": "gateway-log-20260429-001", "role": "r6"},
            )
        except ConfirmationRequiredError:
            pass
        else:
            raise AssertionError("gateway log anchoring must require explicit confirmation")

        result = service.invoke_skill(
            "ops.gateway.log.anchor",
            {
                "gateway_log_ref": "gateway-log-20260429-001",
                "resource_code": "api-trace-ledger",
                "source_ref": "dsp-dataservice:apilog/deposit:001",
                "evidence_json": {"failure_count": 1, "nested": {"password": "should-not-persist"}, "token": "should-not-persist"},
                "role": "r6",
                "confirmed": True,
            },
        )

        assert result["ok"] is True
        assert result["result"]["evidence_json"] == {"failure_count": 1, "nested": {}}
        pending = database_store.list_pending_anchor_outbox()
        assert any(item.request_id == result["audit_id"] and item.skill_id == "ops.gateway.log.anchor" for item in pending)
        mappings = database_store.legacy_mapping_repo.list_mappings(canonical_type="anchor_outbox", canonical_ref=result["audit_id"])
        assert mappings[0].legacy_object_ref == "gateway-log-20260429-001"
        events = [item for item in database_store.list_audit_events() if item.skill_id == "ops.gateway.log.anchor"]
        assert [item.phase for item in events] == ["before", "after"]


def test_api_resource_withdraw_and_revoke_update_approval_trace() -> None:
    with TemporaryDirectory() as tmp:
        import os

        db_path = Path(tmp) / "zw_brain.db"
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))

        service.invoke_skill(
            "resource.api.register",
            {
                "resource_code": "api-retire-ledger",
                "title": "撤回撤销 API",
                "source_ref": "dsp-dataservice:api_service_info:api-retire-ledger",
                "role": "r6",
                "confirmed": True,
            },
        )
        service.invoke_skill("resource.api.submit_review", {"resource_code": "api-retire-ledger", "role": "r6", "confirmed": True})
        service.invoke_skill(
            "resource.api.review",
            {"resource_code": "api-retire-ledger", "decision": "approve", "role": "r7", "confirmed": True},
        )
        service.invoke_skill("resource.api.publish", {"resource_code": "api-retire-ledger", "role": "r7", "confirmed": True})
        retired = service.invoke_skill("resource.api.withdraw", {"resource_code": "api-retire-ledger", "role": "r6", "confirmed": True})
        revoked = service.invoke_skill("resource.api.revoke", {"resource_code": "api-retire-ledger", "role": "r7", "confirmed": True})

        assert retired["result"]["lifecycle_status"] == "retired"
        assert revoked["result"]["lifecycle_status"] == "revoked"
        case = next(item for item in database_store.approval_repo.list_cases() if item.application_code == "api-retire-ledger")
        assert case.current_status == "revoked"
        assert database_store.approval_repo.list_steps("api-retire-ledger")[-2].step_name == "API 服务资源撤回"
        assert database_store.approval_repo.list_steps("api-retire-ledger")[-1].step_name == "API 服务资源撤销授权"
        assert [item.decision for item in database_store.approval_repo.list_decisions("api-retire-ledger")][-2:] == ["close", "close"]



    with TemporaryDirectory() as tmp:
        import os

        db_path = Path(tmp) / "zw_brain.db"
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))

        service.invoke_skill(
            "resource.api.register",
            {
                "resource_code": "api-test-ledger",
                "title": "连通性测试 API",
                "role": "r6",
                "confirmed": True,
            },
        )
        result = service.invoke_skill(
            "resource.api.test",
            {
                "resource_code": "api-test-ledger",
                "test_result": "failed",
                "binding_code": "bind-test-ledger",
                "evidence_json": {"latency_ms": 20, "nested": {"secret": "should-not-persist"}, "token": "should-not-persist"},
                "role": "r6",
                "confirmed": True,
            },
        )

        assert result["result"]["lifecycle_status"] == "test_failed"
        assert result["result"]["test_projection"]["evidence_json"] == {"latency_ms": 20, "nested": {}}
        projections = database_store.resource_api_repo.list_test_projections("api-test-ledger")
        assert projections[0].test_ref == result["audit_id"]
        assert projections[0].evidence_json == {"latency_ms": 20, "nested": {}}
        assert any(item.canonical_type == "resource_api_test_projection" for item in database_store.legacy_mapping_repo.list_mappings())


def test_audit_sink_failure_blocks_write_mutation() -> None:
    tmp, service = make_service()
    try:
        def fail_sink(request_id, actor, skill_id, phase, payload):
            raise RuntimeError("audit database unavailable")

        audit_bus.configure_sink(fail_sink)
        try:
            service.invoke_skill("request.create", {"resource_id": "res-market-activity", "role": "r1", "confirmed": True})
        except AuditWriteError:
            pass
        else:
            raise AssertionError("audit persistence failure must block mutation")

        snapshot = service.snapshot()
        assert not any(item["resourceId"] == "res-market-activity" and item["status"] == "pending" for item in snapshot["requests"])
    finally:
        tmp.cleanup()
        audit_bus.clear_sink()


def test_p0_objection_case_closes_with_audited_database_flow() -> None:
    with TemporaryDirectory() as tmp:
        import os

        from sqlalchemy import create_engine, text

        from zw_brain.shared.database_store import DatabaseStore

        os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "zw_brain.db")
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))

        created = service.invoke_skill(
            "objection.case.create",
            {
                "target_type": "delivery",
                "target_id": "DLV-2026-04-25-0011",
                "title": "交付回执结果异议",
                "basis_text": "回执与实际下载状态不一致",
                "expected_result": "重新核查交付链路",
                "role": "r1",
                "confirmed": True,
                "evidence": [{"evidence_type": "text", "content_json": {"token": "secret", "note": "用户截图"}}],
            },
        )
        objection_id = created["result"]["id"]
        assert created["result"]["status"] == "draft"

        for skill_id, payload in [
            ("objection.case.submit", {}),
            ("objection.case.accept", {"role": "r2"}),
            ("objection.case.assign", {"role": "r2", "target_status": "provider_investigating"}),
            ("objection.case.escalate", {"role": "r2", "opinion": "超过 SLA，升级督办", "evidence": [{"evidence_type": "sla", "content_json": {"password": "drop", "days": 3}}]}),
            ("objection.case.reply", {"role": "r6", "opinion": "已完成提供方核查"}),
            ("objection.case.review", {"role": "r2", "decision": "resolve", "resolved_summary": "交付回执已修正"}),
            ("objection.case.evaluate", {"role": "r1", "overall_score": 95, "comment": "处理及时"}),
            ("objection.case.close", {"role": "r2"}),
        ]:
            result = service.invoke_skill(skill_id, {"objection_id": objection_id, "confirmed": True} | payload)
            assert result["ok"] is True

        cases = service.invoke_skill("objection.case.query", {"role": "r2"})
        assert any(item["id"] == objection_id and item["status"] == "closed" for item in cases["items"])
        process = service.invoke_skill("objection.process.query", {"objection_id": objection_id, "role": "r2"})
        assert len(process["items"]) >= 6
        assert any(item["action_type"] == "escalate" and item["action_result"] == "escalated" for item in process["items"])
        assert any(item["content_json"] == {"days": 3} for item in process["evidence"])
        metrics = service.invoke_skill("objection.metric.query", {"role": "r2"})
        assert metrics["closed_count"] >= 1

        engine = create_engine(f"sqlite:///{os.environ['ZW_BRAIN_DB_PATH']}", future=True)
        with engine.connect() as conn:
            assert conn.execute(text("select count(*) from audit_event where skill_id like 'objection.%'")).scalar_one() >= 16
            assert conn.execute(text("select count(*) from anchor_outbox where skill_id like 'objection.%'")).scalar_one() >= 8


def test_p0_objection_invalid_transition_is_rejected() -> None:
    with TemporaryDirectory() as tmp:
        import os

        from zw_brain.shared.database_store import DatabaseStore

        os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "zw_brain.db")
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))
        created = service.invoke_skill(
            "objection.case.create",
            {"target_type": "resource", "target_id": "res-jbxx-ledger", "title": "资源异议", "role": "r1", "confirmed": True},
        )

        try:
            service.invoke_skill("objection.case.close", {"objection_id": created["result"]["id"], "role": "r2", "confirmed": True})
        except InvalidStateError:
            pass
        else:
            raise AssertionError("invalid objection transition must be rejected")


def test_p0_adapter_records_idempotent_receipts_without_canonical_overwrite() -> None:
    with TemporaryDirectory() as tmp:
        import os

        from sqlalchemy import create_engine, text

        from zw_brain.shared.database_store import DatabaseStore

        os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "zw_brain.db")
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))
        before = service.invoke_skill("request.view", {"request_id": "REQ-2026-04-25-0011", "role": "r1"})["status"]

        payload = {
            "local_aggregate_type": "application",
            "local_aggregate_id": "REQ-2026-04-25-0011",
            "external_object_type": "national_application",
            "external_object_id": "NAT-APP-0011",
            "idempotency_key": "national-app-0011",
            "receipt_json": {"status": "accepted", "api_key": "should-not-persist"},
            "extra_json": {"certificate": "should-not-persist", "batch": "B001"},
            "role": "r6",
            "confirmed": True,
        }
        first = service.invoke_skill("adapter.national.application.receive", payload)
        second = service.invoke_skill("adapter.national.application.receive", payload | {"status": "partial", "failure_count": 1})

        assert first["ok"] is True
        assert second["ok"] is True
        assert first["result"]["run"]["id"] == second["result"]["run"]["id"]
        assert second["result"]["run"]["status"] == "partial"
        assert second["result"]["mapping"]["last_receipt_json"] == {"status": "accepted"}
        after = service.invoke_skill("request.view", {"request_id": "REQ-2026-04-25-0011", "role": "r1"})["status"]
        assert after == before

        mappings = service.invoke_skill("adapter.external.mapping.query", {"local_aggregate_id": "REQ-2026-04-25-0011", "role": "r6"})
        assert mappings["total"] == 1
        health = service.invoke_skill("adapter.cascade.health.query", {"role": "r6"})
        assert health["summary"]["run_count"] == 1

        engine = create_engine(f"sqlite:///{os.environ['ZW_BRAIN_DB_PATH']}", future=True)
        with engine.connect() as conn:
            assert conn.execute(text("select count(*) from adapter_run_record")).scalar_one() == 1
            assert conn.execute(text("select count(*) from external_object_mapping")).scalar_one() == 1



def test_p1_governance_and_topic_package_capabilities_with_database() -> None:
    with TemporaryDirectory() as tmp:
        import os

        from sqlalchemy import create_engine, text

        from zw_brain.shared.database_store import DatabaseStore

        os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "zw_brain.db")
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))

        org_sync = service.invoke_skill(
            "org.projection.sync",
            {
                "tenant": {"tenant_id": "default", "tenant_name": "默认租户"},
                "regions": [{"region_code": "370100", "region_name": "济南市"}],
                "orgs": [{"org_code": "ORG-YBT", "org_name": "一表通专班", "region_code": "370100", "profile_json": {"secret": "drop", "kind": "taskforce"}}],
                "roles": [{"role_code": "r7", "role_name": "能力治理员"}],
                "role": "r7",
                "confirmed": True,
            },
        )
        assert org_sync["result"]["orgs"][0]["profile_json"] == {"kind": "taskforce"}

        actor_sync = service.invoke_skill(
            "actor.projection.sync",
            {"external_actor_id": "u-ybt", "display_name": "专题治理员", "org_code": "ORG-YBT", "role_codes": ["r7"], "role": "r7", "confirmed": True},
        )
        assert actor_sync["result"]["items"][0]["role_codes_json"] == ["r7"]

        candidate = service.invoke_skill(
            "legacy.bsp.mapping.import",
            {
                "legacy_permission_ref": "dsp-bsp:sharezone:publish",
                "legacy_role_ref": "ROLE_TOPIC_ADMIN",
                "capability_id": "topic.package.publish",
                "surface": "webui",
                "evidence_json": {"token": "drop", "source": "old-bsp"},
                "role": "r7",
                "confirmed": True,
            },
        )
        assert candidate["result"]["items"][0]["evidence_json"] == {"source": "old-bsp", "manifest_version": "inline-v1", "manifest_source_ref": "legacy:bsp:mapping-manifest:inline-v1"}
        policy_eval = service.invoke_skill("tenant.policy.evaluate", {"capability_id": "topic.package.publish", "role_code": "r7", "role": "r7"})
        assert policy_eval["allowed"] is False
        assert policy_eval["source"] == "fail_closed"
        assert policy_eval["decision_reason"] == "missing_tenant_policy"
        assert policy_eval["legacy_candidates"][0]["legacy_permission_ref"] == "dsp-bsp:sharezone:publish"

        service.invoke_skill(
            "topic.package.create",
            {"package_code": "tp-ybt", "title": "一表通 / 基层报表减负", "owner_org_id": "ORG-YBT", "display_snapshot_json": {"password": "drop", "headline": "基层只补差异"}, "role": "r7", "confirmed": True},
        )
        service.invoke_skill(
            "topic.package.configure",
            {
                "package_code": "tp-ybt",
                "items": [{"item_code": "cat-jbxx", "ref_type": "catalog", "ref_id": "cat-jbxx", "title": "法人基础信息", "summary_json": {"secret": "drop", "domain": "法人"}}],
                "visibility": [{"visibility_code": "r7-web", "role_code": "r7", "policy_status": "approved", "condition_json": {"api_key": "drop", "scope": "governance"}}],
                "role": "r7",
                "confirmed": True,
            },
        )
        service.invoke_skill("topic.package.submit", {"package_code": "tp-ybt", "role": "r7", "confirmed": True})
        published = service.invoke_skill("topic.package.review", {"package_code": "tp-ybt", "decision": "approve", "role": "r7", "confirmed": True})
        assert published["result"]["status"] == "published"
        service.invoke_skill("topic.package.evidence.attach", {"package_code": "tp-ybt", "evidence_type": "case", "title": "减负证据", "content_json": {"certificate": "drop", "saving_hours": 12}, "role": "r7", "confirmed": True})
        service.invoke_skill("topic.package.subscribe", {"package_code": "tp-ybt", "org_code": "ORG-YBT", "role_code": "r1", "role": "r7", "confirmed": True})
        database_store.topic_package_repo.upsert_metric("tp-ybt", {"metric_key": "reuse_count", "metric_value": 2})

        detail = service.invoke_skill("topic.package.query", {"package_code": "tp-ybt", "role": "r7"})["items"][0]
        assert detail["display_snapshot_json"] == {"headline": "基层只补差异"}
        assert detail["items"][0]["summary_json"] == {"domain": "法人"}
        assert any(item["surface"] == "subscription" for item in detail["visibility"])
        metrics = service.invoke_skill("topic.package.metric.query", {"package_code": "tp-ybt", "role": "r7"})
        assert metrics["summary"]["published_count"] == 1
        assert metrics["items"][0]["metric_value"] == 2

        engine = create_engine(f"sqlite:///{os.environ['ZW_BRAIN_DB_PATH']}", future=True)
        with engine.connect() as conn:
            assert conn.execute(text("select count(*) from audit_event where skill_id like 'topic.package.%'")).scalar_one() >= 10
            assert conn.execute(text("select count(*) from anchor_outbox where skill_id like 'topic.package.%'")).scalar_one() >= 5
            assert conn.execute(text("select count(*) from legacy_policy_mapping_candidate")).scalar_one() == 1


def test_p1_governance_actor_projection_accepts_mock_iaf_claims() -> None:
    with TemporaryDirectory() as tmp:
        import os

        from zw_brain.shared.database_store import DatabaseStore

        os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "zw_brain.db")
        os.environ["ZW_BRAIN_IAF_ISSUER"] = "https://iaf.example/realms/picp"
        os.environ["ZW_BRAIN_IAF_AUDIENCE"] = "zw-brain"
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))

        claims = {
            "sub": "iaf-user-001",
            "iss": "https://iaf.example/realms/picp",
            "aud": ["zw-brain"],
            "exp": int((datetime.now(UTC) + timedelta(minutes=10)).timestamp()),
            "state": "s-1",
            "nonce": "n-1",
            "preferred_username": "zhangsan",
            "project_id": "sd-default",
            "project": "shandong",
            "realm_access": {"roles": ["ACCOUNT_ADMIN", "r7"]},
            "resource_access": {"zw-brain": {"roles": ["r7"]}},
        }
        token = _encode_mock_jwt(claims)

        result = service.invoke_skill(
            "actor.projection.sync",
            {
                "iaf_claims": token,
                "expected_state": "s-1",
                "expected_nonce": "n-1",
                "tenant_id": "default",
                "org_code": "ORG-YBT",
                "role": "r7",
                "confirmed": True,
            },
        )

        item = result["result"]["items"][0]
        snapshot = result["result"]["actor_snapshots"][0]
        assert item["external_actor_id"] == "iaf-user-001"
        assert item["display_name"] == "z*******"
        assert set(item["role_codes_json"]) == {"ACCOUNT_ADMIN", "r7"}
        assert item["profile_json"]["username"] == "zhangsan"
        assert item["profile_json"]["project_id"] == "sd-default"
        assert item["profile_json"]["project"] == "shandong"
        assert item["profile_json"]["iam_role_codes"] == ["r7"]
        assert item["profile_json"]["realm_roles"] == ["ACCOUNT_ADMIN", "r7"]
        assert item["profile_json"]["account_admin"] is True
        assert snapshot["subject"] == "iaf-user-001"
        assert snapshot["tenant_id"] == "default"
        assert snapshot["org_code"] == "ORG-YBT"
        assert set(snapshot["role_codes"]) == {"ACCOUNT_ADMIN", "r7"}
        assert snapshot["iam_role_codes"] == ["r7"]
        assert snapshot["account_flags"]["account_admin"] is True
        assert snapshot["issuer"] == "https://iaf.example/realms/picp"
        assert snapshot["audience"] == ["zw-brain"]
        assert snapshot["project_id"] == "sd-default"
        assert snapshot["project"] == "shandong"


def test_p1_governance_actor_projection_accepts_client_id_when_audience_claim_is_absent() -> None:
    with TemporaryDirectory() as tmp:
        import os

        from zw_brain.shared.database_store import DatabaseStore

        os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "zw_brain.db")
        os.environ["ZW_BRAIN_IAF_ISSUER"] = "https://iaf.example/realms/picp"
        os.environ["ZW_BRAIN_IAF_AUDIENCE"] = "zw-brain"
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))

        token = _encode_mock_jwt(
            {
                "sub": "iaf-user-client-id",
                "iss": "https://iaf.example/realms/picp",
                "client_id": "zw-brain",
                "exp": int((datetime.now(UTC) + timedelta(minutes=10)).timestamp()),
                "state": "s-client-id",
                "nonce": "n-client-id",
                "resource_access": {"zw-brain": {"roles": ["r7"]}},
            }
        )

        result = service.invoke_skill(
            "actor.projection.sync",
            {
                "iaf_claims": token,
                "expected_state": "s-client-id",
                "expected_nonce": "n-client-id",
                "tenant_id": "default",
                "role": "r7",
                "confirmed": True,
            },
        )

        item = result["result"]["items"][0]
        assert item["external_actor_id"] == "iaf-user-client-id"
        assert item["role_codes_json"] == ["r7"]


def _assert_actor_projection_rejects_claims(claims: dict[str, object], *, expected_state: str = "s-2", expected_nonce: str = "n-2") -> None:
    with TemporaryDirectory() as tmp:
        import os

        from zw_brain.shared.database_store import DatabaseStore

        os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "zw_brain.db")
        os.environ["ZW_BRAIN_IAF_ISSUER"] = "https://iaf.example/realms/picp"
        os.environ["ZW_BRAIN_IAF_AUDIENCE"] = "zw-brain"
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))
        token = _encode_mock_jwt(claims)

        try:
            service.invoke_skill(
                "actor.projection.sync",
                {
                    "iaf_claims": token,
                    "expected_state": expected_state,
                    "expected_nonce": expected_nonce,
                    "tenant_id": "default",
                    "role": "r7",
                    "confirmed": True,
                },
            )
        except InvalidTokenError:
            pass
        else:
            raise AssertionError("invalid IAF claims must be rejected")


def _valid_iaf_claims(**overrides: object) -> dict[str, object]:
    claims: dict[str, object] = {
        "sub": "iaf-user-002",
        "iss": "https://iaf.example/realms/picp",
        "aud": ["zw-brain"],
        "exp": int((datetime.now(UTC) + timedelta(minutes=10)).timestamp()),
        "state": "s-2",
        "nonce": "n-2",
    }
    claims.update(overrides)
    return claims


def test_p1_governance_actor_projection_rejects_state_mismatch() -> None:
    _assert_actor_projection_rejects_claims(_valid_iaf_claims(), expected_state="bad")


def test_p1_governance_actor_projection_rejects_nonce_mismatch() -> None:
    _assert_actor_projection_rejects_claims(_valid_iaf_claims(), expected_nonce="bad")


def test_p1_governance_actor_projection_rejects_issuer_mismatch() -> None:
    _assert_actor_projection_rejects_claims(_valid_iaf_claims(iss="https://iaf.example/realms/other"))


def test_p1_governance_actor_projection_rejects_audience_mismatch() -> None:
    _assert_actor_projection_rejects_claims(_valid_iaf_claims(aud=["other-client"]))


def test_p1_governance_actor_projection_rejects_client_id_mismatch() -> None:
    claims = _valid_iaf_claims(client_id="other-client")
    claims.pop("aud")
    _assert_actor_projection_rejects_claims(claims)


def test_p1_governance_actor_projection_rejects_expired_token() -> None:
    _assert_actor_projection_rejects_claims(_valid_iaf_claims(exp=int((datetime.now(UTC) - timedelta(minutes=1)).timestamp())))


def test_p1_governance_actor_projection_rejects_missing_sub() -> None:
    claims = _valid_iaf_claims()
    claims.pop("sub")
    _assert_actor_projection_rejects_claims(claims)


def test_p1_governance_org_and_actor_projection_context_is_complete() -> None:
    with TemporaryDirectory() as tmp:
        import os

        from zw_brain.shared.database_store import DatabaseStore

        os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "zw_brain.db")
        os.environ["ZW_BRAIN_IAF_ISSUER"] = "https://iaf.example/realms/picp"
        os.environ["ZW_BRAIN_IAF_AUDIENCE"] = "zw-brain"
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))

        org_result = service.invoke_skill(
            "org.projection.sync",
            {
                "tenant": {"tenant_id": "default", "tenant_name": "山东省", "profile_json": {"project_id": "sd-default"}},
                "regions": [{"region_code": "370100", "region_name": "济南市", "parent_region_code": "370000", "region_level": "2"}],
                "orgs": [{"org_code": "ORG-YBT", "org_name": "省大数据局", "region_code": "370100"}],
                "roles": [{"role_code": "r7", "role_name": "平台运营"}],
                "role": "r7",
                "confirmed": True,
            },
        )
        assert org_result["result"]["tenant"]["tenant_id"] == "default"
        assert org_result["result"]["orgs"][0]["org_code"] == "ORG-YBT"
        assert org_result["result"]["regions"][0]["region_code"] == "370100"
        assert org_result["result"]["roles"][0]["role_code"] == "r7"

        token = _encode_mock_jwt(
            {
                "sub": "iaf-user-003",
                "iss": "https://iaf.example/realms/picp",
                "aud": ["zw-brain"],
                "exp": int((datetime.now(UTC) + timedelta(minutes=10)).timestamp()),
                "state": "s-3",
                "nonce": "n-3",
                "preferred_username": "lisi",
                "project_id": "sd-default",
                "project": "shandong",
                "realm_access": {"roles": ["ACCOUNT_ADMIN"]},
                "resource_access": {"zw-brain": {"roles": ["r7"]}},
            }
        )
        actor_result = service.invoke_skill(
            "actor.projection.sync",
            {
                "iaf_claims": token,
                "expected_state": "s-3",
                "expected_nonce": "n-3",
                "tenant_id": "default",
                "org_code": "ORG-YBT",
                "role": "r7",
                "confirmed": True,
            },
        )
        snapshot = actor_result["result"]["actor_snapshots"][0]
        assert snapshot["tenant_id"] == "default"
        assert snapshot["org_code"] == "ORG-YBT"
        assert snapshot["status"] == "active"
        assert set(snapshot["role_codes"]) == {"ACCOUNT_ADMIN", "r7"}
        assert snapshot["iam_role_codes"] == ["r7"]
        assert snapshot["project_id"] == "sd-default"
        assert snapshot["project"] == "shandong"
        assert snapshot["account_flags"]["account_admin"] is True

        repo = database_store.governance_projection_repo
        assert [item.tenant_id for item in repo.list_tenants()] == ["default"]
        assert repo.list_orgs(tenant_id="default")[0].org_code == "ORG-YBT"
        assert repo.list_regions(tenant_id="default")[0].region_code == "370100"
        assert repo.list_roles(tenant_id="default")[0].role_code == "r7"
        assert repo.list_actors(tenant_id="default")[0].external_actor_id == "iaf-user-003"


def test_p1_governance_policy_fail_closed_for_unbound_or_inconsistent_actor_context() -> None:
    with TemporaryDirectory() as tmp:
        import os

        from zw_brain.shared.database_store import DatabaseStore

        os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "zw_brain.db")
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))
        service.invoke_skill("package.review_decide", {"package_id": "PKG-2026-04-25-001", "decision": "approve", "role": "r7", "confirmed": True})
        service.invoke_skill("package.register_version", {"package_id": "PKG-2026-04-25-001", "role": "r7", "confirmed": True})
        service.invoke_skill("package.apply_tenant_policy", {"package_id": "PKG-2026-04-25-001", "role": "r7", "confirmed": True})

        base_payload = {
            "tenant_id": "default",
            "capability_id": "ledger.entity.base.read",
            "surface": "api",
            "role": "r7",
            "actor_snapshot": {"tenant_id": "default", "org_code": "ORG-YBT", "role_codes": ["r7"], "status": "active"},
            "org_snapshot": {"tenant_id": "default", "org_code": "ORG-YBT"},
        }
        allowed = service.invoke_skill("tenant.policy.evaluate", base_payload)
        assert allowed["allowed"] is True
        assert allowed["decision_reason"] == "allowed_by_tenant_policy"

        for status, reason in [
            ("unmatched", "actor_unmatched"),
            ("disabled", "actor_disabled"),
            ("iam_account_missing", "iam_account_missing"),
        ]:
            payload = copy.deepcopy(base_payload)
            payload["actor_snapshot"]["status"] = status
            denied = service.invoke_skill("tenant.policy.evaluate", payload)
            assert denied["allowed"] is False
            assert denied["source"] == "fail_closed"
            assert denied["decision_reason"] == reason

        cross_tenant = copy.deepcopy(base_payload)
        cross_tenant["actor_snapshot"]["tenant_id"] = "other-tenant"
        denied = service.invoke_skill("tenant.policy.evaluate", cross_tenant)
        assert denied["allowed"] is False
        assert denied["decision_reason"] == "cross_tenant_denied"

        org_mismatch = copy.deepcopy(base_payload)
        org_mismatch["org_snapshot"]["org_code"] = "ORG-OTHER"
        denied = service.invoke_skill("tenant.policy.evaluate", org_mismatch)
        assert denied["allowed"] is False
        assert denied["decision_reason"] == "org_binding_mismatch"

        role_mismatch = copy.deepcopy(base_payload)
        role_mismatch["role"] = "r6"
        denied = service.invoke_skill("tenant.policy.evaluate", role_mismatch)
        assert denied["allowed"] is False
        assert denied["decision_reason"] == "role_binding_mismatch"


def test_p1_governance_legacy_import_supports_dry_run_and_idempotent_apply() -> None:
    with TemporaryDirectory() as tmp:
        import os

        from zw_brain.shared.database_store import DatabaseStore

        os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "zw_brain.db")
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))

        payload = {
            "mode": "dry-run",
            "rows": [
                {
                    "legacy_permission_ref": "dsp-bsp:sharezone:publish",
                    "legacy_role_ref": "ROLE_TOPIC_ADMIN",
                    "capability_id": "topic.package.publish",
                    "surface": "webui",
                    "source_ref": "dsp-bsp:permission:sharezone:publish",
                    "evidence_json": {"token": "drop", "source": "legacy-bsp"},
                },
                {
                    "legacy_permission_ref": "dsp-bsp:unknown",
                    "legacy_role_ref": "ROLE_UNKNOWN",
                    "capability_id": "unknown.capability",
                    "surface": "webui",
                },
                {
                    "legacy_permission_ref": "dsp-bsp:iam-missing",
                    "legacy_role_ref": "ROLE_X",
                    "capability_id": "topic.package.publish",
                    "candidate_status": "iam_account_missing",
                },
            ],
            "role": "r7",
            "confirmed": True,
        }

        dry_run = service.invoke_skill("legacy.bsp.mapping.import", payload)
        assert dry_run["result"]["mode"] == "dry-run"
        assert dry_run["result"]["summary"]["source_count"] == 3
        assert dry_run["result"]["summary"]["projection_count"] == 1
        assert dry_run["result"]["summary"]["mapping_count"] == 1
        assert dry_run["result"]["summary"]["skip_count"] == 1
        assert dry_run["result"]["summary"]["failure_count"] == 1
        assert dry_run["result"]["summary"]["blockers"]["iam_account_missing"] == 1
        assert dry_run["result"]["summary"]["blockers"]["unmapped_permission"] == 1

        apply_payload = dict(payload)
        apply_payload["mode"] = "apply"
        applied_first = service.invoke_skill("legacy.bsp.mapping.import", apply_payload)
        applied_second = service.invoke_skill("legacy.bsp.mapping.import", apply_payload)
        assert applied_first["result"]["summary"]["projection_count"] == applied_second["result"]["summary"]["projection_count"]

        mappings = database_store.legacy_mapping_repo.list_mappings(canonical_type="capability")
        assert len(mappings) == 1
        assert mappings[0].canonical_ref == "topic.package.publish"
        assert mappings[0].evidence_json == {"source": "legacy-bsp", "manifest_version": "inline-v1", "manifest_source_ref": "legacy:bsp:mapping-manifest:inline-v1"}


def test_p1_governance_legacy_import_reports_all_blockers_and_sanitizes_evidence() -> None:
    with TemporaryDirectory() as tmp:
        import os

        from zw_brain.shared.database_store import DatabaseStore

        os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "zw_brain.db")
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))

        payload = {
            "mode": "dry-run",
            "rows": [
                {
                    "legacy_permission_ref": "dsp-bsp:sharezone:publish",
                    "legacy_role_ref": "ROLE_TOPIC_ADMIN",
                    "capability_id": "topic.package.publish",
                    "surface": "webui",
                    "source_ref": "dsp-bsp:permission:sharezone:publish",
                    "evidence_json": {
                        "source": "legacy-bsp",
                        "password": "drop",
                        "token": "drop",
                        "secret": "drop",
                        "client_secret": "drop",
                        "nested": {"refresh_token": "drop", "keep": "ok"},
                    },
                },
                {
                    "legacy_permission_ref": "dsp-bsp:unmatched",
                    "legacy_role_ref": "ROLE_UNMATCHED",
                    "capability_id": "topic.package.publish",
                    "candidate_status": "unmatched",
                },
                {
                    "legacy_permission_ref": "dsp-bsp:disabled",
                    "legacy_role_ref": "ROLE_DISABLED",
                    "capability_id": "topic.package.publish",
                    "candidate_status": "disabled",
                },
                {
                    "legacy_permission_ref": "dsp-bsp:iam-missing",
                    "legacy_role_ref": "ROLE_IAM_MISSING",
                    "capability_id": "topic.package.publish",
                    "candidate_status": "iam_account_missing",
                },
                {
                    "legacy_permission_ref": "dsp-bsp:unknown",
                    "legacy_role_ref": "ROLE_UNKNOWN",
                    "capability_id": "unknown.capability",
                    "surface": "webui",
                },
            ],
            "role": "r7",
            "confirmed": True,
        }

        dry_run = service.invoke_skill("legacy.bsp.mapping.import", payload)
        summary = dry_run["result"]["summary"]
        assert summary["source_count"] == 5
        assert summary["projection_count"] == 1
        assert summary["mapping_count"] == 1
        assert summary["skip_count"] == 3
        assert summary["failure_count"] == 1
        assert summary["blockers"] == {"iam_account_missing": 1, "unmatched": 2, "unmapped_permission": 1}
        planned = dry_run["result"]["items"][0]
        assert planned["result"] == "planned"
        assert planned["evidence_json"] == {"source": "legacy-bsp", "nested": {"keep": "ok"}, "manifest_version": "inline-v1", "manifest_source_ref": "legacy:bsp:mapping-manifest:inline-v1"}
        assert dry_run["result"]["items"][1]["reason"] == "unmatched"
        assert dry_run["result"]["items"][2]["reason"] == "disabled"
        assert dry_run["result"]["items"][3]["reason"] == "iam_account_missing"
        assert dry_run["result"]["items"][4]["reason"] == "unmapped_permission"
        assert database_store.governance_projection_repo.list_policy_candidates() == []
        assert database_store.legacy_mapping_repo.list_mappings(canonical_type="capability") == []


def test_p1_governance_legacy_import_idempotent_and_conflict_safe() -> None:
    with TemporaryDirectory() as tmp:
        import os

        from zw_brain.shared.database_store import DatabaseStore

        os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "zw_brain.db")
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))
        payload = {
            "mode": "apply",
            "rows": [
                {
                    "legacy_permission_ref": "dsp-bsp:sharezone:publish",
                    "legacy_role_ref": "ROLE_TOPIC_ADMIN",
                    "capability_id": "topic.package.publish",
                    "surface": "webui",
                    "source_ref": "dsp-bsp:permission:sharezone:publish",
                    "evidence_json": {"source": "legacy-bsp", "token": "drop"},
                }
            ],
            "role": "r7",
            "confirmed": True,
        }

        first = service.invoke_skill("legacy.bsp.mapping.import", payload)
        second = service.invoke_skill("legacy.bsp.mapping.import", payload)
        assert first["result"]["summary"] == second["result"]["summary"]
        assert first["result"]["items"][0]["result"] == "applied"
        candidates = database_store.governance_projection_repo.list_policy_candidates()
        assert len(candidates) == 1
        assert candidates[0].capability_id == "topic.package.publish"
        mappings = database_store.legacy_mapping_repo.list_mappings(canonical_type="capability")
        assert len(mappings) == 1
        assert mappings[0].canonical_ref == "topic.package.publish"
        assert mappings[0].mapping_status == "mapped"
        assert mappings[0].evidence_json == {"source": "legacy-bsp", "manifest_version": "inline-v1", "manifest_source_ref": "legacy:bsp:mapping-manifest:inline-v1"}

        conflict_payload = copy.deepcopy(payload)
        conflict_payload["rows"] = [
            {
                "legacy_permission_ref": "dsp-bsp:sharezone:publish",
                "legacy_role_ref": "ROLE_TOPIC_ADMIN",
                "capability_id": "topic.package.subscribe",
                "surface": "webui",
                "source_ref": "dsp-bsp:permission:sharezone:publish",
                "evidence_json": {"source": "legacy-bsp-conflict", "client_secret": "drop"},
            }
        ]
        conflict = service.invoke_skill("legacy.bsp.mapping.import", conflict_payload)
        assert conflict["result"]["summary"]["mapping_count"] == 1
        mappings_after_conflict = database_store.legacy_mapping_repo.list_mappings(canonical_type="capability")
        assert len(mappings_after_conflict) == 2
        by_ref = {item.canonical_ref: item for item in mappings_after_conflict}
        assert by_ref["topic.package.publish"].mapping_status == "conflicted"
        assert by_ref["topic.package.publish"].evidence_json == {"source": "legacy-bsp", "manifest_version": "inline-v1", "manifest_source_ref": "legacy:bsp:mapping-manifest:inline-v1"}
        assert by_ref["topic.package.subscribe"].mapping_status == "conflicted"
        assert by_ref["topic.package.subscribe"].evidence_json == {"source": "legacy-bsp-conflict", "manifest_version": "inline-v1", "manifest_source_ref": "legacy:bsp:mapping-manifest:inline-v1"}


def test_p1_governance_mapping_manifest_explicit_versioned_and_sanitized() -> None:
    with TemporaryDirectory() as tmp:
        import os

        from zw_brain.shared.database_store import DatabaseStore

        os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "zw_brain.db")
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))
        payload = {
            "mode": "apply",
            "mapping_manifest": {
                "manifest_version": "bsp-governance-v2026-05-09",
                "source_ref": "legacy:bsp:mapping-manifest:bsp-governance-v2026-05-09",
                "rows": [
                    {
                        "legacy_permission_ref": "dsp-bsp:sharezone:publish",
                        "legacy_role_ref": "ROLE_TOPIC_ADMIN",
                        "capability_id": "topic.package.publish",
                        "surface": "webui",
                        "source_ref": "dsp-bsp:permission:sharezone:publish",
                        "evidence_json": {
                            "reviewed_by": "governance-board",
                            "password": "drop",
                            "token": "drop",
                            "secret": "drop",
                            "client_secret": "drop",
                            "menu_tree": {"legacy": "drop"},
                            "button_permission_tree": {"legacy": "drop"},
                            "permission_sql": "select * from sys_permission",
                            "legacy_url": "/bsp/menu/tree",
                            "route_component": "OldMenu.vue",
                        },
                    }
                ],
            },
            "role": "r7",
            "confirmed": True,
        }

        applied = service.invoke_skill("legacy.bsp.mapping.import", payload)
        item = applied["result"]["items"][0]
        assert item["manifest_version"] == "bsp-governance-v2026-05-09"
        assert item["manifest_source_ref"] == "legacy:bsp:mapping-manifest:bsp-governance-v2026-05-09"
        assert item["evidence_json"] == {
            "reviewed_by": "governance-board",
            "manifest_version": "bsp-governance-v2026-05-09",
            "manifest_source_ref": "legacy:bsp:mapping-manifest:bsp-governance-v2026-05-09",
        }
        candidates = database_store.governance_projection_repo.list_policy_candidates()
        assert len(candidates) == 1
        assert candidates[0].evidence_json == item["evidence_json"]
        mappings = database_store.legacy_mapping_repo.list_mappings(canonical_type="capability")
        assert len(mappings) == 1
        assert mappings[0].evidence_json == item["evidence_json"]


def test_p1_governance_policy_decision_and_import_receipts_are_auditable_and_sanitized() -> None:
    with TemporaryDirectory() as tmp:
        import os

        from zw_brain.shared.database_store import DatabaseStore

        os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "zw_brain.db")
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))
        service.invoke_skill("package.review_decide", {"package_id": "PKG-2026-04-25-001", "decision": "approve", "role": "r7", "confirmed": True})
        service.invoke_skill("package.register_version", {"package_id": "PKG-2026-04-25-001", "role": "r7", "confirmed": True})
        service.invoke_skill("package.apply_tenant_policy", {"package_id": "PKG-2026-04-25-001", "role": "r7", "confirmed": True})
        actor_snapshot = {
            "subject": "iaf-user-audit",
            "tenant_id": "default",
            "org_code": "ORG-YBT",
            "role_codes": ["r7"],
            "iam_role_codes": ["r7"],
            "account_flags": {"account_admin": False},
        }
        decision = service.invoke_skill(
            "tenant.policy.evaluate",
            {
                "tenant_id": "default",
                "capability_id": "ledger.entity.base.read",
                "surface": "api",
                "role": "r7",
                "actor_snapshot": actor_snapshot,
                "org_snapshot": {"tenant_id": "default", "org_code": "ORG-YBT"},
                "risk_context": {"password": "drop", "token": "drop", "client_secret": "drop", "certificate": "drop", "safe": "keep"},
            },
        )
        assert decision["allowed"] is True
        import_result = service.invoke_skill(
            "legacy.bsp.mapping.import",
            {
                "mode": "apply",
                "mapping_manifest": {
                    "manifest_version": "audit-v1",
                    "source_ref": "legacy:bsp:mapping-manifest:audit-v1",
                    "rows": [
                        {
                            "legacy_permission_ref": "dsp-bsp:sys-log-history",
                            "legacy_role_ref": "ROLE_TOPIC_ADMIN",
                            "capability_id": "topic.package.publish",
                            "surface": "webui",
                            "source_ref": "dsp-bsp:sys_log:history-only",
                            "evidence_json": {
                                "source_kind": "historical_sys_log_evidence",
                                "sys_log_ref": "sys_log:42",
                                "password": "drop",
                                "token": "drop",
                                "client_secret": "drop",
                                "private_key": "drop",
                                "operator_phone": "13800001111",
                            },
                        }
                    ],
                },
                "role": "r7",
                "confirmed": True,
            },
        )
        assert import_result["audit_id"].startswith("AE-")
        assert import_result["result"]["audit_id"] == import_result["audit_id"]
        item = import_result["result"]["items"][0]
        assert item["evidence_json"] == {
            "source_kind": "historical_sys_log_evidence",
            "sys_log_ref": "sys_log:42",
            "operator_phone": "13800001111",
            "manifest_version": "audit-v1",
            "manifest_source_ref": "legacy:bsp:mapping-manifest:audit-v1",
        }
        calls = database_store.list_capability_calls()
        policy_call = next(item for item in calls if item.skill_id == "tenant.policy.evaluate" and item.output_json.get("decision_reason") == "allowed_by_tenant_policy")
        assert policy_call.input_json["actor_snapshot"] == actor_snapshot
        assert policy_call.input_json["risk_context"] == {"safe": "keep"}
        assert policy_call.output_json["policy"]
        assert policy_call.output_json["decision_reason"] == "allowed_by_tenant_policy"
        import_call = next(item for item in calls if item.skill_id == "legacy.bsp.mapping.import")
        assert import_call.output_json["items"][0]["evidence_json"] == item["evidence_json"]
        assert "password" not in import_call.input_json["mapping_manifest"]["rows"][0]["evidence_json"]
        assert "token" not in import_call.input_json["mapping_manifest"]["rows"][0]["evidence_json"]
        audit_events = database_store.list_audit_events()
        policy_after = next(item for item in audit_events if item.skill_id == "tenant.policy.evaluate" and item.phase == "after" and item.payload_json.get("decision_reason") == "allowed_by_tenant_policy")
        assert policy_after.payload_json["actor_snapshot"] == actor_snapshot
        import_after = next(item for item in audit_events if item.skill_id == "legacy.bsp.mapping.import" and item.phase == "after")
        assert import_after.request_id == import_result["audit_id"]
        assert import_after.payload_json["items"][0]["evidence_json"] == item["evidence_json"]
        sys_log_policy = service.invoke_skill("tenant.policy.evaluate", {"capability_id": "topic.package.publish", "surface": "webui", "role": "r7", "risk_context": {"source_kind": "historical_sys_log_evidence"}})
        assert sys_log_policy["allowed"] is False
        assert sys_log_policy["decision_reason"] == "missing_tenant_policy"


def test_p1_governance_policy_fails_closed_without_capability_id_or_mapping_manifest() -> None:
    with TemporaryDirectory() as tmp:
        import os

        from zw_brain.shared.database_store import DatabaseStore

        os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "zw_brain.db")
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))

        missing_capability = service.invoke_skill("tenant.policy.evaluate", {"surface": "api", "role": "r7"})
        assert missing_capability["allowed"] is False
        assert missing_capability["source"] == "fail_closed"
        assert missing_capability["decision_reason"] == "missing_capability_id"
        assert missing_capability["legacy_candidates"] == []

        unmapped_import = service.invoke_skill(
            "legacy.bsp.mapping.import",
            {
                "mode": "dry-run",
                "rows": [{"legacy_permission_ref": "dsp-bsp:unknown", "legacy_role_ref": "ROLE_UNKNOWN", "capability_id": "unknown.capability", "surface": "webui"}],
                "role": "r7",
                "confirmed": True,
            },
        )
        assert unmapped_import["result"]["summary"]["failure_count"] == 1
        assert unmapped_import["result"]["summary"]["blockers"]["unmapped_permission"] == 1

        denied = service.invoke_skill("tenant.policy.evaluate", {"capability_id": "unknown.capability", "surface": "webui", "role": "r7"})
        assert denied["allowed"] is False
        assert denied["source"] == "fail_closed"
        assert denied["decision_reason"] == "missing_tenant_policy"
        assert denied["legacy_candidates"] == []


def test_p1_governance_legacy_candidate_cannot_bypass_missing_or_restrictive_tenant_policy() -> None:
    with TemporaryDirectory() as tmp:
        import os

        from zw_brain.shared.database_store import DatabaseStore

        os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "zw_brain.db")
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))

        import_payload = {
            "mode": "apply",
            "rows": [
                {
                    "legacy_permission_ref": "dsp-bsp:sharezone:publish",
                    "legacy_role_ref": "ROLE_TOPIC_ADMIN",
                    "capability_id": "topic.package.publish",
                    "surface": "webui",
                    "source_ref": "dsp-bsp:permission:sharezone:publish",
                }
            ],
            "role": "r7",
            "confirmed": True,
        }
        imported = service.invoke_skill("legacy.bsp.mapping.import", import_payload)
        assert imported["result"]["summary"]["mapping_count"] == 1

        missing_policy = service.invoke_skill("tenant.policy.evaluate", {"capability_id": "topic.package.publish", "surface": "webui", "role": "r7"})
        assert missing_policy["allowed"] is False
        assert missing_policy["source"] == "fail_closed"
        assert missing_policy["decision_reason"] == "missing_tenant_policy"
        assert missing_policy["legacy_candidates"][0]["legacy_permission_ref"] == "dsp-bsp:sharezone:publish"

        service.invoke_skill(
            "capability.package.register",
            {
                "package_id": "PKG-topic-package-publish",
                "slug": "topic.package.publish",
                "source": "zw-brain registry",
                "status": "pending",
                "exposure": ["api"],
                "role": "r7",
                "confirmed": True,
            },
        )
        service.invoke_skill("capability.version.review", {"package_id": "PKG-topic-package-publish", "decision": "approve", "role": "r7", "confirmed": True})
        service.invoke_skill("package.register_version", {"package_id": "PKG-topic-package-publish", "role": "r7", "confirmed": True})
        service.invoke_skill("package.apply_tenant_policy", {"package_id": "PKG-topic-package-publish", "role": "r7", "confirmed": True})

        surface_denied = service.invoke_skill("tenant.policy.evaluate", {"capability_id": "topic.package.publish", "surface": "webui", "role": "r7"})
        assert surface_denied["allowed"] is False
        assert surface_denied["source"] == "tenant_capability_policy"
        assert surface_denied["decision_reason"] == "surface_not_exposed"
        assert surface_denied["legacy_candidates"][0]["capability_id"] == "topic.package.publish"

        service.invoke_skill("tenant.capability.disable", {"package_id": "PKG-topic-package-publish", "role": "r7", "confirmed": True})
        disabled = service.invoke_skill("tenant.policy.evaluate", {"capability_id": "topic.package.publish", "surface": "webui", "role": "r7"})
        assert disabled["allowed"] is False
        assert disabled["source"] == "tenant_capability_policy"
        assert disabled["decision_reason"] == "tenant_policy_disabled"
        assert disabled["legacy_candidates"][0]["legacy_permission_ref"] == "dsp-bsp:sharezone:publish"


def test_p1_governance_account_admin_cannot_bypass_policy_denies_or_confirmation() -> None:
    with TemporaryDirectory() as tmp:
        import os

        from zw_brain.shared.database_store import DatabaseStore

        os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "zw_brain.db")
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))

        account_admin_actor = {
            "subject": "iaf-account-admin",
            "tenant_id": "default",
            "org_code": "ORG-YBT",
            "status": "active",
            "role_codes": ["r7", "ACCOUNT_ADMIN"],
            "iam_role_codes": ["r7"],
            "account_flags": {"account_admin": True},
        }
        base_payload = {
            "tenant_id": "default",
            "capability_id": "ledger.entity.base.read",
            "surface": "api",
            "role": "r7",
            "actor_snapshot": account_admin_actor,
            "org_snapshot": {"tenant_id": "default", "org_code": "ORG-YBT"},
        }

        missing_policy_payload = copy.deepcopy(base_payload)
        missing_policy_payload["capability_id"] = "topic.package.publish"
        missing_policy = service.invoke_skill("tenant.policy.evaluate", missing_policy_payload)
        assert missing_policy["allowed"] is False
        assert missing_policy["source"] == "fail_closed"
        assert missing_policy["decision_reason"] == "missing_tenant_policy"
        assert missing_policy["actor_snapshot"]["account_flags"]["account_admin"] is True

        service.invoke_skill("package.review_decide", {"package_id": "PKG-2026-04-25-001", "decision": "approve", "role": "r7", "confirmed": True})
        service.invoke_skill("package.register_version", {"package_id": "PKG-2026-04-25-001", "role": "r7", "confirmed": True})
        service.invoke_skill("package.apply_tenant_policy", {"package_id": "PKG-2026-04-25-001", "role": "r7", "confirmed": True})

        allowed = service.invoke_skill("tenant.policy.evaluate", base_payload)
        assert allowed["allowed"] is True
        assert allowed["decision_reason"] == "allowed_by_tenant_policy"

        surface_denied_payload = copy.deepcopy(base_payload)
        surface_denied_payload["surface"] = "webui"
        surface_denied = service.invoke_skill("tenant.policy.evaluate", surface_denied_payload)
        assert surface_denied["allowed"] is False
        assert surface_denied["source"] == "tenant_capability_policy"
        assert surface_denied["decision_reason"] == "surface_not_exposed"

        cross_tenant_payload = copy.deepcopy(base_payload)
        cross_tenant_payload["actor_snapshot"]["tenant_id"] = "other-tenant"
        cross_tenant = service.invoke_skill("tenant.policy.evaluate", cross_tenant_payload)
        assert cross_tenant["allowed"] is False
        assert cross_tenant["source"] == "fail_closed"
        assert cross_tenant["decision_reason"] == "cross_tenant_denied"

        service.invoke_skill("tenant.capability.disable", {"package_id": "PKG-2026-04-25-001", "role": "r7", "confirmed": True})
        disabled = service.invoke_skill("tenant.policy.evaluate", base_payload)
        assert disabled["allowed"] is False
        assert disabled["source"] == "tenant_capability_policy"
        assert disabled["decision_reason"] == "tenant_policy_disabled"

        try:
            service.invoke_skill("approval.review_decide", {"request_id": "REQ-2026-04-25-0011", "decision": "approve", "role": "r2"})
        except ConfirmationRequiredError as exc:
            assert str(exc) == "approval.review_decide"
        else:
            raise AssertionError("high-risk write skill must require explicit confirmation")


def test_p1_governance_tenant_policy_evaluate_fail_closed_surface_matrix() -> None:
    with TemporaryDirectory() as tmp:
        import os

        from zw_brain.shared.database_store import DatabaseStore

        os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "zw_brain.db")
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))

        service.invoke_skill(
            "package.review_decide",
            {
                "package_id": "PKG-2026-04-25-001",
                "decision": "approve",
                "role": "r7",
                "confirmed": True,
            },
        )
        service.invoke_skill(
            "package.register_version",
            {"package_id": "PKG-2026-04-25-001", "role": "r7", "confirmed": True},
        )
        service.invoke_skill(
            "package.apply_tenant_policy",
            {"package_id": "PKG-2026-04-25-001", "role": "r7", "confirmed": True},
        )

        by_surface = {
            surface: service.invoke_skill(
                "tenant.policy.evaluate",
                {
                    "capability_id": "ledger.entity.base.read",
                    "surface": surface,
                    "role": "r7",
                },
            )
            for surface in ["webui", "api", "cli", "mcp", "a2a"]
        }

        assert by_surface["api"]["allowed"] is True
        assert by_surface["api"]["source"] == "tenant_capability_policy"
        assert by_surface["api"]["decision_reason"] == "allowed_by_tenant_policy"
        for surface in ["webui", "cli", "mcp", "a2a"]:
            assert by_surface[surface]["allowed"] is False
            assert by_surface[surface]["source"] == "tenant_capability_policy"
            assert by_surface[surface]["decision_reason"] == "surface_not_exposed"

        no_policy = service.invoke_skill(
            "tenant.policy.evaluate",
            {
                "capability_id": "topic.package.publish",
                "surface": "webui",
                "role": "r7",
            },
        )
        assert no_policy["allowed"] is False
        assert no_policy["source"] == "fail_closed"
        assert no_policy["decision_reason"] == "missing_tenant_policy"


def test_p1_governance_cold_start_runtime_does_not_call_legacy_bsp_online_services(monkeypatch) -> None:
    with TemporaryDirectory() as tmp:
        import os
        import socket
        from urllib import request as urllib_request

        from zw_brain.shared.database_store import DatabaseStore

        os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "zw_brain.db")
        os.environ["ZW_BRAIN_TENANT_ID"] = "default"
        os.environ.pop("ZW_BRAIN_LEGACY_BSP_BASE_URL", None)
        os.environ.pop("ZW_BRAIN_UCENTER_BASE_URL", None)
        from zw_brain.shared.migrate import ensure_runtime_schema

        def legacy_bsp_unavailable(*args: object, **kwargs: object) -> None:
            raise AssertionError("runtime governance path must not call legacy BSP or ucenter online services")

        monkeypatch.setattr(socket, "create_connection", legacy_bsp_unavailable)
        monkeypatch.setattr(urllib_request, "urlopen", legacy_bsp_unavailable)
        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))

        org_result = service.invoke_skill(
            "org.projection.sync",
            {
                "tenant_id": "default",
                "tenant": {"tenant_id": "default", "tenant_name": "山东省", "source_ref": "dsp-bsp:tenant:default"},
                "regions": [{"region_code": "370100", "region_name": "济南市", "parent_region_code": "370000", "region_level": "2", "source_ref": "dsp-bsp:pub_region:370100"}],
                "orgs": [{"org_code": "11370000MB284651XL", "org_name": "省大数据局", "region_code": "370100", "source_ref": "dsp-bsp:pub_organ:11370000MB284651XL"}],
                "roles": [{"role_code": "r7", "role_name": "平台治理员", "source_ref": "dsp-bsp:pub_role:r7"}],
                "role": "r7",
                "confirmed": True,
            },
        )
        assert org_result["result"]["tenant"]["tenant_id"] == "default"

        claims = _encode_mock_jwt(
            {
                "sub": "iaf-user-cold-start",
                "iss": "https://iaf.example/realms/picp",
                "aud": ["zw-brain"],
                "exp": int((datetime.now(UTC) + timedelta(minutes=10)).timestamp()),
                "state": "state-cold",
                "nonce": "nonce-cold",
                "preferred_username": "governance-admin",
                "project_id": "sd-default",
                "project": "shandong",
                "realm_access": {"roles": ["ACCOUNT_ADMIN"]},
                "resource_access": {"zw-brain": {"roles": ["r7"]}},
            }
        )
        actor_result = service.invoke_skill(
            "actor.projection.sync",
            {
                "iaf_claims": claims,
                "expected_state": "state-cold",
                "expected_nonce": "nonce-cold",
                "tenant_id": "default",
                "org_code": "11370000MB284651XL",
                "role": "r7",
                "confirmed": True,
            },
        )
        actor_snapshot = actor_result["result"]["actor_snapshots"][0]
        assert actor_snapshot["tenant_id"] == "default"
        assert actor_snapshot["org_code"] == "11370000MB284651XL"
        assert actor_snapshot["iam_role_codes"] == ["r7"]
        assert actor_snapshot["account_flags"]["account_admin"] is True

        import_result = service.invoke_skill(
            "legacy.bsp.mapping.import",
            {
                "tenant_id": "default",
                "mode": "apply",
                "mapping_manifest": {
                    "manifest_version": "cold-start-v1",
                    "source_ref": "legacy:bsp:mapping-manifest:cold-start-v1",
                    "rows": [
                        {
                            "legacy_permission_ref": "dsp-bsp:sharezone:publish",
                            "legacy_role_ref": "ROLE_TOPIC_ADMIN",
                            "capability_id": "topic.package.publish",
                            "surface": "api",
                            "source_ref": "dsp-bsp:permission:sharezone:publish",
                            "evidence_json": {"source_kind": "historical_sys_log_evidence", "sys_log_ref": "sys_log:9001", "token": "drop"},
                        }
                    ],
                },
                "role": "r7",
                "confirmed": True,
            },
        )
        assert import_result["result"]["summary"]["mapping_count"] == 1
        assert import_result["result"]["items"][0]["evidence_json"] == {
            "source_kind": "historical_sys_log_evidence",
            "sys_log_ref": "sys_log:9001",
            "manifest_version": "cold-start-v1",
            "manifest_source_ref": "legacy:bsp:mapping-manifest:cold-start-v1",
        }

        service.invoke_skill(
            "capability.package.register",
            {
                "tenant_id": "default",
                "package_id": "PKG-topic-package-publish-cold",
                "slug": "topic.package.publish",
                "source": "zw-brain registry",
                "status": "pending",
                "exposure": ["api", "cli", "mcp", "a2a", "webui"],
                "role": "r7",
                "confirmed": True,
            },
        )
        service.invoke_skill("capability.version.review", {"package_id": "PKG-topic-package-publish-cold", "decision": "approve", "role": "r7", "confirmed": True})
        service.invoke_skill("package.register_version", {"package_id": "PKG-topic-package-publish-cold", "role": "r7", "confirmed": True})
        enable_result = service.invoke_skill("tenant.capability.enable", {"tenant_id": "default", "package_id": "PKG-topic-package-publish-cold", "role": "r7", "confirmed": True})
        assert enable_result["result"]["tenant_id"] == "default"

        policy_eval = service.invoke_skill(
            "tenant.policy.evaluate",
            {
                "tenant_id": "default",
                "capability_id": "topic.package.publish",
                "surface": "api",
                "role": "r7",
                "actor_snapshot": actor_snapshot,
                "org_snapshot": {"tenant_id": "default", "org_code": "11370000MB284651XL"},
            },
        )
        assert policy_eval["allowed"] is True
        assert policy_eval["source"] == "tenant_capability_policy"
        assert policy_eval["policy"]["exposedSurfaces"] == ["api"]
        assert policy_eval["legacy_candidates"][0]["legacy_permission_ref"] == "dsp-bsp:sharezone:publish"
        assert policy_eval["legacy_candidates"][0]["evidence_json"]["source_kind"] == "historical_sys_log_evidence"

        business_view = service.invoke_skill("request.view", {"request_id": "REQ-2026-04-25-0011", "role": "r1"})
        registry_view = service.invoke_skill("registry.artifact.export", {"role": "r7"})
        assert business_view["id"] == "REQ-2026-04-25-0011"
        assert any(item["skill_id"] == "topic.package.publish" for item in registry_view["items"])
        assert any(package["slug"] == "topic.package.publish" and package["tenantPolicy"]["tenantId"] == "default" for package in registry_view["packages"])

        repo = database_store.governance_projection_repo
        assert repo.list_tenants()[0].tenant_id == "default"
        assert repo.list_regions(tenant_id="default")[0].source_ref == "dsp-bsp:pub_region:370100"
        assert repo.list_orgs(tenant_id="default")[0].source_ref == "dsp-bsp:pub_organ:11370000MB284651XL"
        assert repo.list_roles(tenant_id="default")[0].source_ref == "dsp-bsp:pub_role:r7"
        assert repo.list_actors(tenant_id="default")[0].source_ref == "iaf:claims"
        assert database_store.capability_package_repo.get_policy("topic.package.publish", tenant_id="default") is not None

        calls = database_store.list_capability_calls()
        assert any(item.skill_id == "request.view" and item.status == "succeeded" for item in calls)
        assert any(item.skill_id == "tenant.policy.evaluate" and item.output_json["decision_reason"] == "allowed_by_tenant_policy" for item in calls)
        assert any(item.skill_id == "legacy.bsp.mapping.import" for item in calls)
        audit_events = database_store.list_audit_events()
        assert any(item.skill_id == "tenant.policy.evaluate" and item.phase == "after" and item.payload_json["allowed"] is True for item in audit_events)
        assert any(item.skill_id == "legacy.bsp.mapping.import" and item.phase == "after" for item in audit_events)


def test_p1_governance_no_legacy_runtime_compat_or_dual_read_write_contracts() -> None:
    from zw_brain.entry.rest import server as rest_server_module
    from zw_brain.skill_registration.runtime import load_manifests

    openapi = json.loads(rest_server_module.OPENAPI_PATH.read_text(encoding="utf-8"))
    forbidden_paths = {"/bsp/", "/login", "/oauth2Login", "/SAML2/", "/cas/"}
    assert not any(any(fragment in path for fragment in forbidden_paths) for path in openapi["paths"])
    assert set(openapi["paths"]).issubset({"/health", "/openapi.json", "/api/snapshot"} | {f"/api/skills/{skill_id}" for skill_id in load_manifests()})

    server_source = Path(rest_server_module.__file__).read_text(encoding="utf-8")
    assert "/api/skills/" in server_source
    forbidden_runtime_fragments = {
        "/bsp/",
        "/login",
        "/oauth2Login",
        "/SAML2/",
        "/cas/",
        "ucenter",
        "fallback_login",
        "lightweight_login",
        "legacy_bsp_service",
        "dual_read",
        "dual_write",
        "double_read",
        "double_write",
    }
    assert not any(fragment in server_source for fragment in forbidden_runtime_fragments)

    for manifest in load_manifests().values():
        runtime_binding = manifest.get("runtime_binding") or {}
        assert runtime_binding.get("kind") != "legacy_bsp_service"
        assert "ucenter" not in json.dumps(manifest, ensure_ascii=False)
        if manifest["skill_id"] != "legacy.bsp.mapping.import":
            assert "sys_log" not in json.dumps(manifest, ensure_ascii=False).lower()


def test_p1_topic_package_publish_requires_approved_visibility() -> None:
    with TemporaryDirectory() as tmp:
        import os

        from zw_brain.shared.database_store import DatabaseStore

        os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "zw_brain.db")
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))
        service.invoke_skill("topic.package.create", {"package_code": "tp-blocked", "title": "未满足发布条件", "role": "r7", "confirmed": True})
        service.invoke_skill("topic.package.submit", {"package_code": "tp-blocked", "role": "r7", "confirmed": True})
        try:
            service.invoke_skill("topic.package.publish", {"package_code": "tp-blocked", "role": "r7", "confirmed": True})
        except InvalidStateError:
            pass
        else:
            raise AssertionError("topic package must not publish without item and approved visibility")


def test_mask_layer_applied_to_actor_and_topic_serializers() -> None:
    """The read-side mask must catch every PII-bearing serializer in BrainService.

    Regression for [2026-05-06] sensitive-field policy: any payload returned to a
    REST/CLI/Skill caller must run through apply_field_masks at default role
    (external) so phones / names / emails / id_cards / addresses are masked.
    """
    from types import SimpleNamespace

    from zw_brain.command.brain import BrainService
    from zw_brain.shared.state_store import StateStore

    service = BrainService(state_store=StateStore())

    actor = SimpleNamespace(
        external_actor_id="uid-1",
        display_name="高大量",
        org_code="11370000MB284651XL",
        role_codes_json=["r-admin"],
        status="active",
        source_ref="dsp-bsp:pub_user:uid-1",
        profile_json={
            "phone": "13800001111",
            "mobile": "13800001112",
            "email": "high@sd.gov.cn",
            "identity_num": "370101199001011234",
            "address": "山东省济南市某街 1 号",
            "org_name": "省大数据局",
        },
    )
    out = service._actor_projection_record_to_dict(actor)
    assert out["display_name"] == "高**"
    assert out["profile_json"]["phone"] == "138****1111"
    assert out["profile_json"]["mobile"] == "138****1112"
    assert out["profile_json"]["email"] == "h***@***"
    assert out["profile_json"]["identity_num"] == "*" * 18
    assert out["profile_json"]["address"] == "***"
    assert out["profile_json"]["org_name"] == "省大数据局"  # not masked

    package = SimpleNamespace(
        package_code="eg-1",
        title="婚姻登记",
        scenario="一表通",
        owner_org_id="11370000MB284651XL",
        owner_org_snapshot_json={"org_name": "省大数据局"},
        status="published",
        display_snapshot_json={"contacts": [{"contact_name": "韩岩", "contact_phone": "15585294353"}]},
        metric_snapshot_json={},
        source_ref="dsp-sharezone:data_example:eg-1",
    )
    out = service._topic_package_record_to_dict(package)
    contact = out["display_snapshot_json"]["contacts"][0]
    assert contact["contact_name"] == "韩*"
    assert contact["contact_phone"] == "155****4353"

    # process record handler_snapshot_json (objection process) — handler_phone must mask
    process = SimpleNamespace(
        id="proc-1",
        objection_id="obj-1",
        node_name="核查",
        handler_org_id="org-1",
        handler_snapshot_json={"handler_name": "李明", "handler_phone": "17887990701"},
        action_type="investigate",
        action_result="pass",
        opinion="处理意见",
        created_at=__import__("datetime").datetime(2026, 1, 1),
    )
    out = service._process_record_to_dict(process)
    assert out["handler_snapshot_json"]["handler_name"] == "李*"
    assert out["handler_snapshot_json"]["handler_phone"] == "178****0701"


def test_data_search_recalls_real_catalog_dictionary_titles() -> None:
    """A2 closure: data.search must surface real-catalog candidates from the
    discovery.recallDictionary even when no discovery card matches.

    "教师资格" never appears in the 12 demo cards, but does appear in a real
    dsp_metaresource title that the importer wired into recallDictionary. The
    search result must include it as a `recall_dictionary` candidate so the NL
    accelerator has a real surface to point at.
    """
    tmp, service = make_service()
    try:
        result = service.invoke_skill("data.search", {"query": "教师资格", "role": "r1"})
        recall_hits = [it for it in result["results"] if it.get("kind") == "recall_dictionary"]
        assert recall_hits, "recallDictionary must surface 教师资格 candidate"
        assert any("教师资格" in it["name"] for it in recall_hits)
        default_result = service.invoke_skill("data.search", {"query": "停车场信息", "role": "r1"})
        assert default_result["results"][0]["id"] == "res-jbxx-ledger"
        # Empty query must NOT spam recall (would dump 25 thin cards on every page load)
        empty_result = service.invoke_skill("data.search", {"query": "", "role": "r1"})
        assert not any(it.get("kind") == "recall_dictionary" for it in empty_result["results"])
    finally:
        tmp.cleanup()


def test_catalog_browse_paginates_active_real_entries() -> None:
    """A new browse skill must paginate canonical catalog_entry rows with
    sensible defaults: lifecycle=active filters out retired/draft noise, and
    kind=real excludes the api-group:* nodes that bulk-import from
    dsp_service.api_group inflates the table with."""
    with TemporaryDirectory() as tmp:
        import os

        os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "zw_brain.db")
        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        ds = DatabaseStore()
        audit_bus.configure_sink(ds.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=ds))

        # Seed a few catalog entries spanning lifecycle + kind axes.
        ds.catalog_repo.upsert_from_resource(
            {"id": "cat-real-A", "name": "真业务目录 A", "status": "active", "provider": "org-x"}
        )
        ds.catalog_repo.upsert_from_resource(
            {"id": "cat-real-B", "name": "真业务目录 B", "status": "active", "provider": "org-y"}
        )
        ds.catalog_repo.upsert_from_resource(
            {"id": "cat-retired-X", "name": "废弃目录 X", "status": "retired", "provider": "org-x"}
        )
        ds.catalog_repo.upsert_from_resource(
            {"id": "api-group:1", "name": "API 分组 1", "status": "active", "provider": "org-x"}
        )

        # Default call: lifecycle=active, kind=real, page=1, limit=20
        result = service.invoke_skill("catalog.browse", {"role": "r1"})
        assert result["page"] == 1
        assert result["limit"] == 20
        assert result["total"] >= 2
        assert all(it["lifecycle_status"] == "active" for it in result["items"])
        assert all(not it["catalog_code"].startswith("api-group:") for it in result["items"])
        assert {"cat-real-A", "cat-real-B"}.issubset({it["catalog_code"] for it in result["items"]})
        assert "cat-retired-X" not in {it["catalog_code"] for it in result["items"]}

        # Pagination caps page size correctly.
        page1 = service.invoke_skill("catalog.browse", {"role": "r1", "limit": 1})
        assert page1["page"] == 1
        assert page1["limit"] == 1
        assert len(page1["items"]) == 1
        page2 = service.invoke_skill("catalog.browse", {"role": "r1", "limit": 1, "page": 2})
        assert page2["page"] == 2
        assert page2["items"][0]["catalog_code"] != page1["items"][0]["catalog_code"]

        # limit clamps to 100 (defends against client passing absurd values).
        clamped = service.invoke_skill("catalog.browse", {"role": "r1", "limit": 999})
        assert clamped["limit"] == 100
        # Negative limit clamps up to 1.
        floor = service.invoke_skill("catalog.browse", {"role": "r1", "limit": -5})
        assert floor["limit"] == 1

        # kind=api-group surfaces only the api-group:* node
        api_only = service.invoke_skill("catalog.browse", {"role": "r1", "kind": "api-group"})
        assert all(it["catalog_code"].startswith("api-group:") for it in api_only["items"])
        assert api_only["total"] >= 1

        # lifecycle=retired surfaces the retired entry
        retired_only = service.invoke_skill("catalog.browse", {"role": "r1", "lifecycle": "retired"})
        assert "cat-retired-X" in {it["catalog_code"] for it in retired_only["items"]}


def test_catalog_resource_view_opens_catalog_entry_not_in_curated_cards() -> None:
    """Browse rows are catalog_entry records, not necessarily one of the 12 curated cards.
    Detail links must resolve through the repository instead of falling back to the first card.
    """
    tmp, service = make_database_service()
    try:
        store = service._state_store.database_store
        assert store is not None
        store.catalog_repo.upsert_from_resource(
            {"id": "api-group:detail", "name": "浏览详情测试分组", "status": "active", "provider": "platform"}
        )

        detail = service.invoke_skill("catalog.resource_view", {"resource_id": "api-group:detail", "role": "r1"})
        assert detail["id"] == "api-group:detail"
        assert detail["name"] == "浏览详情测试分组"
        assert detail["explain"]
        assert detail["nextHints"]
        assert detail["repository"]["catalogCode"] == "api-group:detail"
    finally:
        tmp.cleanup()


def test_catalog_resource_view_raises_when_neither_snapshot_nor_db_has_id() -> None:
    """R-002: Snapshot AND DB double-miss must surface as NotFoundError, not silently
    return {}. Otherwise the WebUI's resourceById fallback masquerades the failure as
    'first curated card', and detail page renders ${item.name} as undefined."""
    from zw_brain.command.brain import NotFoundError

    tmp, service = make_database_service()
    try:
        raised = False
        try:
            service.invoke_skill(
                "catalog.resource_view",
                {"resource_id": "does-not-exist-anywhere", "role": "r1"},
            )
        except NotFoundError:
            raised = True
        assert raised, "expected NotFoundError when resource is missing in both snapshot and DB"
    finally:
        tmp.cleanup()


def test_data_search_empty_query_keeps_curated_cards_in_database_mode() -> None:
    """P2 discovery first render passes an empty query. In DB mode it must keep
    the curated 12-card homepage, not dump every catalog_entry into the card
    renderer (catalog_entry rows lack explain/nextHints/score and would white-screen).
    """
    tmp, service = make_database_service()
    try:
        result = service.invoke_skill("data.search", {"query": "", "role": "r1"})
        assert result["total"] == 12
        assert all({"explain", "nextHints", "score", "coverage", "updatedAt"} <= set(item) for item in result["results"])
        assert any(item["id"] == "res-jbxx-ledger" for item in result["results"])
    finally:
        tmp.cleanup()


def test_data_search_database_results_are_card_shaped() -> None:
    tmp, service = make_database_service()
    try:
        store = service._state_store.database_store
        assert store is not None
        store.catalog_repo.upsert_from_resource(
            {"id": "cat-search-demo", "name": "教师资格目录", "status": "active", "provider": "org-teacher"}
        )

        result = service.invoke_skill("data.search", {"query": "教师资格", "role": "r1"})
        hit = next(item for item in result["results"] if item["id"] == "cat-search-demo")
        assert hit["name"] == "教师资格目录"
        assert hit["explain"]
        assert hit["nextHints"]
        assert hit["score"] >= 1
    finally:
        tmp.cleanup()
