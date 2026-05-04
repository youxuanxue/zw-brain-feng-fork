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

        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.database_store import DatabaseStore

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

        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.database_store import DatabaseStore

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

        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.database_store import DatabaseStore

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

        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.database_store import DatabaseStore

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

        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.database_store import DatabaseStore

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

        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.database_store import DatabaseStore

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

        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.database_store import DatabaseStore

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

        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.database_store import DatabaseStore

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
