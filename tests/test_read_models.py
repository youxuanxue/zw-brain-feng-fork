from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

# test_dashboard_skill_is_read_only 已删除（K12 大屏 + dashboard.render_command_center Skill 退役 R17 / v4.1）


def test_snapshot_contains_expected_collections() -> None:
    tmp, service = make_service()
    try:
        snapshot = service.invoke_skill("system.snapshot", {})
        for key in ["workbench", "discovery", "requests", "delivery_tasks", "capability_packages", "state"]:
            assert key in snapshot
    finally:
        tmp.cleanup()


def test_schema_info_is_exposed() -> None:
    tmp, service = make_service()
    try:
        result = service.invoke_skill("system.schema_info", {})
        names = [item["name"] for item in result["schemas"]]
        assert names == ["brain_core", "brain_audit", "brain_registry"]
    finally:
        tmp.cleanup()


def make_service() -> tuple[TemporaryDirectory[str], object]:
    tmp = TemporaryDirectory()
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.state_store import StateStore

    store = StateStore(Path(tmp.name) / "brain_state.json")
    return tmp, BrainService(state_store=store)


def test_repository_backed_list_views_include_projected_data() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.command.brain import BrainService
        from zw_brain.shared import audit as audit_bus
        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.state_store import StateStore

        ensure_runtime_schema()
        store = DatabaseStore()
        audit_bus.configure_sink(store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=store))
        service.invoke_skill("approval.review_decide", {"request_id": "REQ-2026-04-25-0011", "decision": "approve", "role": "ROLE_ORGAN_MANAGER", "confirmed": True})

        requests = service.invoke_skill("request.list", {})["items"]
        packages = service.invoke_skill("package.list", {})["items"]
        audit_items = service.invoke_skill("audit.list", {})["items"]

        request = next(item for item in requests if item["id"] == "REQ-2026-04-25-0011")
        package = next(item for item in packages if item["id"] == "PKG-2026-04-25-001")

        assert request["repository"]["application_code"] == "REQ-2026-04-25-0011"
        assert package["tenantPolicy"]["tenantId"] == "sd-default"
        assert any(item["type"] == "approval.review_decide.before" for item in audit_items)
        assert any(item["type"] == "approval.review_decide.after" for item in audit_items)


def test_repository_backed_discovery_reads_include_projected_data() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.command.brain import BrainService
        from zw_brain.shared import audit as audit_bus
        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.state_store import StateStore

        ensure_runtime_schema()
        store = DatabaseStore()
        audit_bus.configure_sink(store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=store))
        store.sync_aggregate_tables(service.snapshot())

        results = service.invoke_skill("data.search", {"query": "法人"})
        resource = service.invoke_skill("catalog.resource_view", {"resource_id": "res-jbxx-ledger"})

        assert results["results"]
        assert results["results"][0]["repository"]["catalogCode"]
        assert resource["repository"]["catalogCode"] == "res-jbxx-ledger"
        assert resource["repository"]["lifecycleStatus"] == resource["status"]


def test_repository_backed_ops_views_include_projected_data() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.command.brain import BrainService
        from zw_brain.shared import audit as audit_bus
        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.state_store import StateStore

        ensure_runtime_schema()
        store = DatabaseStore()
        audit_bus.configure_sink(store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=store))
        service.invoke_skill("approval.review_decide", {"request_id": "REQ-2026-04-25-0011", "decision": "approve_with_supplement", "role": "ROLE_ORGAN_MANAGER", "confirmed": True})
        service.invoke_skill("supplement.submit", {"request_id": "REQ-2026-04-25-0011", "role": "ROLE_ORGAN_OPERATER", "confirmed": True})
        service.invoke_skill("summary.confirm", {"request_id": "REQ-2026-04-25-0011", "role": "ROLE_ORGAN_MANAGER", "confirmed": True})
        service.invoke_skill("delivery.reconcile_receipt", {"task_id": "DLV-2026-04-25-0011", "role": "ROLE_ORGAN_MANAGER", "confirmed": True})
        service.invoke_skill("backflow.confirm", {"task_id": "DLV-2026-04-25-0011", "role": "ROLE_ORGAN_MANAGER", "confirmed": True})

        provider = service.invoke_skill("provider.view", {})
        zones = service.invoke_skill("zone.list", {})["items"]
        business_zone = service.invoke_skill("zone.view", {"zone_id": "business"})

        assert provider["repository"]["resourceCatalogCode"] == "res-jbxx-ledger"
        assert provider["repository"]["packageCount"] >= 1
        assert provider["repository"]["deliveryReceiptCount"] >= 1
        assert any(item["id"] == "business" and item["repository"]["resourceCatalogCode"] == "res-jbxx-ledger" for item in zones)
        assert business_zone["repository"]["resourceCatalogCode"] == "res-jbxx-ledger"
        assert "resourceLifecycleStatus" in business_zone["repository"]
        assert business_zone["trust"]
        assert provider["catalogs"][0]["issue"] == "v1.3 版本说明已同步"
        assert any("模板版本：v1.3" in item for item in business_zone["trust"])


def test_backend_skills_cover_main_webui_detail_routes() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.command.brain import BrainService
        from zw_brain.shared import audit as audit_bus
        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.state_store import StateStore

        ensure_runtime_schema()
        store = DatabaseStore()
        audit_bus.configure_sink(store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=store))
        service.invoke_skill("approval.review_decide", {"request_id": "REQ-2026-04-25-0011", "decision": "approve", "role": "ROLE_ORGAN_MANAGER", "confirmed": True})

        request = service.invoke_skill("request.view", {"request_id": "REQ-2026-04-25-0011"})
        approval = service.invoke_skill("approval.view", {"request_id": "REQ-2026-04-25-0011"})
        delivery = service.invoke_skill("delivery.view", {"task_id": "DLV-2026-04-25-0011"})
        provider = service.invoke_skill("provider.view", {})
        zone = service.invoke_skill("zone.view", {"zone_id": "business"})
        package = service.invoke_skill("package.view", {"package_id": "PKG-2026-04-25-001"})

        assert request["id"] == "REQ-2026-04-25-0011"
        assert approval["id"] == "REQ-2026-04-25-0011"
        assert delivery["id"] == "DLV-2026-04-25-0011"
        assert provider["repository"]["resourceCatalogCode"] == "res-jbxx-ledger"
        assert zone["id"] == "business"
        assert package["id"] == "PKG-2026-04-25-001"
        # dashboard.render_command_center Skill 已退役 (R17 / v4.1)


def test_repository_backed_list_skills_cover_live_pages() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.command.brain import BrainService
        from zw_brain.shared import audit as audit_bus
        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.state_store import StateStore

        ensure_runtime_schema()
        store = DatabaseStore()
        audit_bus.configure_sink(store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=store))
        service.invoke_skill("approval.review_decide", {"request_id": "REQ-2026-04-25-0011", "decision": "approve", "role": "ROLE_ORGAN_MANAGER", "confirmed": True})

        workbench = service.invoke_skill("workbench.view", {"role": "ROLE_ORGAN_MANAGER"})
        requests = service.invoke_skill("request.list", {})
        deliveries = service.invoke_skill("delivery.list", {})
        disputes = service.invoke_skill("governance.dispute_list", {})
        packages = service.invoke_skill("package.list", {})
        zones = service.invoke_skill("zone.list", {})

        assert workbench["todos"]
        assert requests["items"]
        assert deliveries["items"]
        assert disputes["items"]
        assert disputes["alerts"]
        assert disputes["tickets"]
        assert disputes["knowledgeArticles"]
        assert packages["items"]
        assert zones["items"]


def test_governance_list_exposes_alert_ticket_and_knowledge_payloads() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.command.brain import BrainService
        from zw_brain.shared import audit as audit_bus
        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.state_store import StateStore

        ensure_runtime_schema()
        store = DatabaseStore()
        audit_bus.configure_sink(store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=store))
        store.sync_aggregate_tables(service.snapshot())

        disputes = service.invoke_skill("governance.dispute_list", {})
        dispute = next(item for item in disputes["items"] if item["id"] == "DSP-2026-04-25-0003")
        assert disputes["items"]
        assert disputes["alerts"]
        assert disputes["tickets"]
        assert disputes["knowledgeArticles"]
        assert dispute["repository"]["objectionKind"] == "usage"
        assert "evaluation" in dispute


def test_compliance_page_inputs_can_be_refreshed_from_live_skills() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.command.brain import BrainService
        from zw_brain.shared import audit as audit_bus
        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.state_store import StateStore

        ensure_runtime_schema()
        store = DatabaseStore()
        audit_bus.configure_sink(store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=store))
        service.invoke_skill("approval.review_decide", {"request_id": "REQ-2026-04-25-0011", "decision": "approve", "role": "ROLE_ORGAN_MANAGER", "confirmed": True})

        disputes = service.invoke_skill("governance.dispute_list", {})
        audit = service.invoke_skill("audit.list", {})

        assert disputes["items"]
        assert audit["items"]


def test_recovery_and_exposure_controls_project_into_live_reads() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.command.brain import BrainService
        from zw_brain.shared import audit as audit_bus
        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.state_store import StateStore

        ensure_runtime_schema()
        store = DatabaseStore()
        audit_bus.configure_sink(store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=store))
        service.invoke_skill("delivery.trigger_recovery", {"task_id": "DLV-2026-04-23-0004", "role": "ROLE_ORGAN_MANAGER", "confirmed": True})
        service.invoke_skill("package.review_decide", {"package_id": "PKG-2026-04-25-001", "decision": "approve", "role": "ROLE_BUSIAUDIT", "confirmed": True})
        service.invoke_skill("package.register_version", {"package_id": "PKG-2026-04-25-001", "role": "ROLE_BUSIAUDIT", "confirmed": True})
        service.invoke_skill("package.configure_exposure", {"package_id": "PKG-2026-04-25-001", "mode": "expand", "role": "ROLE_BUSIAUDIT", "confirmed": True})

        delivery = service.invoke_skill("delivery.view", {"task_id": "DLV-2026-04-23-0004"})
        package = service.invoke_skill("package.view", {"package_id": "PKG-2026-04-25-001"})

        assert delivery["status"] == "warning"
        assert package["exposure"]
        assert "a2a" in package["exposure"]
        assert "a2a" in package["compatibility"]


def test_dispute_controls_project_into_live_reads() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.command.brain import BrainService
        from zw_brain.shared import audit as audit_bus
        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.state_store import StateStore

        ensure_runtime_schema()
        store = DatabaseStore()
        audit_bus.configure_sink(store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=store))
        service.invoke_skill("compliance.investigate_case", {"dispute_id": "DSP-2026-04-25-0003", "action": "progress", "role": "ROLE_SECURITY_AUDIT", "confirmed": True})
        service.invoke_skill("compliance.investigate_case", {"dispute_id": "DSP-2026-04-25-0003", "action": "escalate", "role": "ROLE_SECURITY_AUDIT", "confirmed": True})

        dispute = service.invoke_skill("governance.dispute_view", {"dispute_id": "DSP-2026-04-25-0003"})
        assert dispute["status"] == "escalated"
        assert dispute["process"]
        assert dispute["evaluation"]
        assert any(step["label"] == "升级治理" for step in dispute["timeline"])


def test_evidence_replay_exposes_audit_and_evidence_chain() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.command.brain import BrainService
        from zw_brain.shared import audit as audit_bus
        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.state_store import StateStore

        ensure_runtime_schema()
        store = DatabaseStore()
        audit_bus.configure_sink(store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=store))
        service.invoke_skill("compliance.investigate_case", {"dispute_id": "DSP-2026-04-25-0003", "action": "progress", "role": "ROLE_SECURITY_AUDIT", "confirmed": True})

        replay = service.invoke_skill("audit.replay_evidence_chain", {"dispute_id": "DSP-2026-04-25-0003"})
        assert replay["disputeId"] == "DSP-2026-04-25-0003"
        assert replay["evidenceChain"]
        assert replay["auditEvents"]
        assert replay["tickets"]
        assert replay["knowledgeArticles"]


def test_package_detail_exposes_registry_and_tenant_policy_projection() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.command.brain import BrainService
        from zw_brain.shared import audit as audit_bus
        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.state_store import StateStore

        ensure_runtime_schema()
        store = DatabaseStore()
        audit_bus.configure_sink(store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=store))
        service.invoke_skill("package.review_decide", {"package_id": "PKG-2026-04-25-001", "decision": "approve", "role": "ROLE_BUSIAUDIT", "confirmed": True})
        service.invoke_skill("package.register_version", {"package_id": "PKG-2026-04-25-001", "role": "ROLE_BUSIAUDIT", "confirmed": True})
        service.invoke_skill("package.apply_tenant_policy", {"package_id": "PKG-2026-04-25-001", "role": "ROLE_BUSIAUDIT", "confirmed": True})

        package = service.invoke_skill("package.view", {"package_id": "PKG-2026-04-25-001"})
        assert package["registeredVersion"] == "v1.0.0"
        assert package["versionStatus"] == "registered"
        assert package["tenantPolicy"]["policyStatus"] == "enabled"
        assert package["tenantScope"] == "sd-default"


def test_provider_publishing_controls_project_into_live_reads() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.command.brain import BrainService
        from zw_brain.shared import audit as audit_bus
        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.state_store import StateStore

        ensure_runtime_schema()
        store = DatabaseStore()
        audit_bus.configure_sink(store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=store))
        service.invoke_skill("catalog.manage_entry", {"catalog_id": "cat-business", "action": "publish", "role": "ROLE_ORGAN_MANAGER", "confirmed": True})
        service.invoke_skill("resource.manage_asset", {"resource_id": "res-company-visit", "action": "publish", "role": "ROLE_ORGAN_MANAGER", "confirmed": True})
        service.invoke_skill("zone.publish_topic_projection", {"zone_id": "business", "role": "ROLE_BUSIAUDIT", "confirmed": True})

        provider = service.invoke_skill("provider.view", {})
        zone = service.invoke_skill("zone.view", {"zone_id": "business"})

        catalog_item = next(item for item in provider["catalogs"] if item["id"] == "cat-business")
        resource_item = next(item for item in provider["resources"] if item["id"] == "res-company-visit")
        assert catalog_item["status"] == "已发布"
        assert resource_item["status"] == "可共享"
        assert zone["status"] == "已发布"
