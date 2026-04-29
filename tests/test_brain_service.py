from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from zw_brain.command.brain import AccessDeniedError, BrainService, ConfirmationRequiredError, InvalidStateError
from zw_brain.shared import audit as audit_bus
from zw_brain.shared.audit import AuditWriteError, drain as drain_audit
from zw_brain.shared.queue import drain as drain_queue
from zw_brain.shared.state_store import StateStore


def make_service() -> tuple[TemporaryDirectory[str], BrainService]:
    tmp = TemporaryDirectory()
    audit_bus.configure_sink(lambda request_id, actor, skill_id, phase, payload: None)
    store = StateStore(Path(tmp.name) / "brain_state.json")
    return tmp, BrainService(state_store=store)


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


def test_full_golden_path_reaches_backflow_confirmed() -> None:
    tmp, service = make_service()
    try:
        service.invoke_skill("approval.review_decide", {"request_id": "REQ-2026-04-25-0011", "decision": "approve", "role": "r2", "confirmed": True})
        service.invoke_skill("supplement.submit", {"request_id": "REQ-2026-04-25-0011", "role": "r3", "confirmed": True})
        service.invoke_skill("summary.confirm", {"request_id": "REQ-2026-04-25-0011", "role": "r5", "confirmed": True})
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




def test_gateway_heartbeat_ingest_is_idempotent_with_database() -> None:
    with TemporaryDirectory() as tmp:
        import os

        db_path = Path(tmp) / "zw_brain.db"
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.database_store import DatabaseStore

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))

        service.invoke_skill(
            "ops.gateway.heartbeat.ingest",
            {
                "gateway_instance_id": "gw-api-main",
                "gateway_address_ref": "gw-ref-main",
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
        assert any(item.skill_id == "ops.gateway.heartbeat.ingest" for item in database_store.list_audit_events())


def test_service_invocation_query_reads_projection_metrics() -> None:
    with TemporaryDirectory() as tmp:
        import os

        db_path = Path(tmp) / "zw_brain.db"
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.database_store import DatabaseStore

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
                "failure_count": 2,
                "error_count": 1,
                "avg_latency_ms": 83,
                "source_event_ref": "metric-ref-1",
            }
        )

        result = service.invoke_skill("ops.service.invocation.query", {"resource_code": "api-custom-ledger", "role": "r6"})

        assert result["summary"]["invokeCount"] == 42
        assert result["summary"]["failureCount"] == 2
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
                "summary_json": {"domain": "法人基础信息", "secret": "should-not-persist"},
                "channel_binding": {
                    "binding_code": "bind-company-ledger",
                    "route_ref": "route-ref-company-ledger",
                    "auth_ref": "auth-ref-company-ledger",
                    "gateway_policy_json": {"rate_limit": "1000/m", "token": "should-not-persist"},
                },
                "role": "r6",
                "confirmed": True,
            },
        )
        assert registered["result"]["lifecycle_status"] == "draft"
        assert "secret" not in registered["result"]["summary_json"]

        service.invoke_skill("resource.api.submit_review", {"resource_code": "api-company-ledger", "role": "r6", "confirmed": True})
        service.invoke_skill(
            "resource.api.review",
            {"resource_code": "api-company-ledger", "decision": "approve", "role": "r7", "confirmed": True},
        )
        published = service.invoke_skill("resource.api.publish", {"resource_code": "api-company-ledger", "role": "r7", "confirmed": True})
        assert published["result"]["lifecycle_status"] == "published"

        policy_update = service.invoke_skill(
            "resource.api.policy.update",
            {
                "resource_code": "api-company-ledger",
                "binding_code": "bind-company-ledger",
                "gateway_policy_json": {"rate_limit": "800/m", "password": "should-not-persist"},
                "role": "r6",
                "confirmed": True,
            },
        )
        assert policy_update["result"]["gateway_policy_json"] == {"rate_limit": "800/m"}
    finally:
        tmp.cleanup()

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
