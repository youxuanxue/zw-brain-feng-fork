from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory


def test_catalog_repository_upserts_resource() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "repo.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.domain.repositories.catalog import CatalogRepository
        from zw_brain.domain.repositories.legacy_mapping import LegacyObjectMappingRepository

        ensure_runtime_schema()
        repo = CatalogRepository()
        resource = {
            "id": "res-demo",
            "name": "示例目录模板",
            "status": "published",
            "provider": "区政数局",
            "region_code": "370100",
            "source_ref": "dsp-dataservice:api_service_catalog:cat-demo",
            "legacy_object_ref": "cat-demo",
            "summary": {"secret": "should-not-persist"},
        }
        repo.upsert_from_resource(resource)
        repo.upsert_item(
            {
                "item_code": "group-demo",
                "catalog_code": "res-demo",
                "resource_code": "api-demo",
                "title": "示例目录分组",
                "item_kind": "group",
                "display_order": 1,
                "source_ref": "dsp-dataservice:api_group:group-demo",
                "legacy_object_ref": "group-demo",
                "summary_json": {"secret": "should-not-persist"},
            }
        )
        records = repo.list_entries()
        assert any(item.catalog_code == "res-demo" and item.region_code == "370100" for item in records)
        items = repo.list_items("res-demo")
        assert items[0].item_code == "group-demo"
        assert items[0].summary_json == {}
        mappings = LegacyObjectMappingRepository().list_mappings(canonical_type="catalog_entry")
        assert any(item.legacy_object_ref == "cat-demo" for item in mappings)
        item_mappings = LegacyObjectMappingRepository().list_mappings(canonical_type="catalog_item")
        assert any(item.legacy_object_ref == "group-demo" for item in item_mappings)


def test_application_repository_writes_legacy_mapping_and_sanitizes_payload() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "repo.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.domain.repositories.application import ApplicationRepository
        from zw_brain.domain.repositories.legacy_mapping import LegacyObjectMappingRepository

        ensure_runtime_schema()
        repo = ApplicationRepository()
        repo.upsert_from_request(
            {
                "id": "REQ-api-app-1",
                "status": "pending",
                "applicant": "申请人",
                "applicantDept": "申请部门",
                "resourceId": "api-one",
                "source_ref": "dsp-dataservice:api_service_app:app-1",
                "legacy_object_ref": "app-1",
                "access": {"secret": "should-not-persist"},
            }
        )

        record = next(item for item in repo.list_records() if item.application_code == "REQ-api-app-1")
        assert record.payload_json["access"] == {}
        mappings = LegacyObjectMappingRepository().list_mappings(canonical_type="application_record")
        assert any(item.legacy_object_ref == "app-1" for item in mappings)

def test_delivery_repository_sanitizes_payload_and_keeps_access_grant_snapshot() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "repo.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.domain.repositories.delivery import DeliveryRepository

        ensure_runtime_schema()
        repo = DeliveryRepository()
        repo.upsert_from_delivery(
            {
                "id": "DLV-api-app-1",
                "requestId": "REQ-api-app-1",
                "status": "completed",
                "channel": "API 授权交付",
                "resourceId": "api-one",
                "access": {
                    "auth_ref": "auth-ref-api-one",
                    "policy_ref": "policy-ref-api-one",
                    "secret": "should-not-persist",
                    "superior_app_secret": "should-not-persist",
                },
                "backflow": {"token": "should-not-persist"},
            }
        )

        record = next(item for item in repo.list_tasks() if item.delivery_code == "DLV-api-app-1")
        assert record.payload_json["access"] == {"auth_ref": "auth-ref-api-one", "policy_ref": "policy-ref-api-one"}
        assert record.payload_json["access_grant_snapshot"] == {
            "resource_code": "api-one",
            "application_code": "REQ-api-app-1",
            "grant_ref": "auth-ref-api-one",
            "policy_ref": "policy-ref-api-one",
            "status": "completed",
        }
        assert record.payload_json["backflow"] == {}

def test_safe_json_removes_sensitive_key_variants() -> None:
    from zw_brain.shared.sanitization import safe_json

    assert safe_json(
        {
            "access_token": "x",
            "refresh_token": "x",
            "client_secret": "x",
            "Authorization": "Bearer x",
            "Cookie": "sid=x",
            "session_key": "x",
            "nested": [{"public": "ok", "db_password_hash": "x", "credentialRef": "x"}],
        }
    ) == {"nested": [{"public": "ok"}]}


    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "repo.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.domain.repositories.resource_api import ResourceApiRepository

        ensure_runtime_schema()
        repo = ResourceApiRepository()
        repo.upsert_asset(
            {
                "resource_code": "api-field-map",
                "title": "字段映射 API",
                "owner_org_id": "ORG-1",
                "owner_org_snapshot_json": {"org_name": "区政数局", "secret": "should-not-persist"},
                "region_code": "370100",
                "access_policy_json": {"share_type": "conditional", "token": "should-not-persist"},
                "qos_policy_json": {"frequency_num": 100, "password": "should-not-persist"},
                "source_ref": "dsp-dataservice:api_service_info:api-field-map",
            }
        )
        repo.upsert_binding(
            {
                "binding_code": "bind-field-map",
                "resource_code": "api-field-map",
                "endpoint_ref": {"rest_method": "POST", "proxy_url": "gateway-route-ref", "secret": "should-not-persist"},
                "schema_ref": {"input": ["id"], "output": ["ok"], "token": "should-not-persist"},
                "auth_ref": "auth-ref-api-field-map",
                "gateway_policy_json": {"frequency_num": 100, "app_secret": "should-not-persist"},
                "source_ref": "dsp-dataservice:api_service_proxy:bind-field-map",
            }
        )

        asset = repo.get_asset("api-field-map")
        assert asset is not None
        assert asset.owner_org_snapshot_json == {"org_name": "区政数局"}
        assert asset.region_code == "370100"
        assert asset.access_policy_json == {"share_type": "conditional"}
        assert asset.qos_policy_json == {"frequency_num": 100}
        binding = repo.get_binding("bind-field-map")
        assert binding is not None
        assert binding.endpoint_ref == {"rest_method": "POST", "proxy_url": "gateway-route-ref"}
        assert binding.schema_ref == {"input": ["id"], "output": ["ok"]}
        assert binding.gateway_policy_json == {"frequency_num": 100}


def test_service_invocation_metric_repository_keeps_region_granularity_and_error_attribution() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "repo.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.domain.repositories.service_invocation import ServiceInvocationMetricRepository

        ensure_runtime_schema()
        repo = ServiceInvocationMetricRepository()
        repo.upsert_metric(
            {
                "metric_scope": "provider_region",
                "resource_code": "api-field-map",
                "provider_org_id": "ORG-1",
                "consumer_org_id": "ORG-2",
                "provider_region_code": "370100",
                "consumer_region_code": "370200",
                "bucket_granularity": "hour",
                "time_bucket": "2026-04-29T10",
                "invoke_count": 10,
                "success_count": 8,
                "failed_count": 2,
                "provider_error_count": 1,
                "consumer_error_count": 1,
                "gateway_error_count": 0,
                "other_error_count": 0,
                "apply_count": 3,
                "avg_latency_ms": 120,
                "p95_latency_ms": 260,
                "last_error_code": "E_PROVIDER",
                "source_event_ref": "dsp-dataservice:api_service_times:metric-1",
            }
        )
        repo.upsert_metric(
            {
                "metric_scope": "provider_region",
                "resource_code": "api-field-map",
                "provider_org_id": "ORG-1",
                "consumer_org_id": "ORG-2",
                "provider_region_code": "370100",
                "consumer_region_code": "370200",
                "bucket_granularity": "hour",
                "time_bucket": "2026-04-29T10",
                "invoke_count": 11,
                "success_count": 9,
                "failed_count": 2,
                "provider_error_count": 2,
            }
        )

        metric = repo.list_metrics(resource_code="api-field-map")[0]
        assert metric.provider_region_code == "370100"
        assert metric.consumer_region_code == "370200"
        assert metric.bucket_granularity == "hour"
        assert metric.invoke_count == 11
        assert metric.failed_count == 2
        assert metric.provider_error_count == 2
        assert metric.consumer_error_count == 1
        assert metric.apply_count == 3
        assert metric.p95_latency_ms == 260


def test_catalog_metadata_core_repositories_persist_reconstruction_evidence() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "repo.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.domain.repositories.catalog import CatalogRepository
        from zw_brain.domain.repositories.metadata_evidence import MetadataEvidenceRepository
        from zw_brain.domain.repositories.legacy_mapping import LegacyObjectMappingRepository

        ensure_runtime_schema()
        catalog_repo = CatalogRepository()
        evidence_repo = MetadataEvidenceRepository()

        catalog_repo.upsert_model(
            {
                "model_code": "legal-person-base",
                "title": "法人单位基础信息模板",
                "status": "active",
                "model_schema_json": {"secret": "should-not-persist", "fields": ["name", "credit_code"]},
                "source_ref": "dsp-catalog3:model_catalog_template:tpl-1",
                "legacy_object_ref": "tpl-1",
            }
        )
        catalog_repo.upsert_model_field(
            {
                "model_code": "legal-person-base",
                "field_code": "credit_code",
                "title": "统一社会信用代码",
                "data_type": "string",
                "sensitive_level": "restricted",
                "field_policy_json": {"token": "should-not-persist", "share_condition": "审批后共享"},
                "source_ref": "dsp-catalog3:model_properties:field-1",
                "legacy_object_ref": "field-1",
            }
        )
        catalog_repo.create_entry_version(
            {
                "catalog_code": "cat-legal-person",
                "version_no": "v1",
                "version_status": "active",
                "snapshot_json": {"password": "should-not-persist", "items": ["credit_code"]},
                "audit_ref": "audit-cat-v1",
                "created_by": "r2",
            }
        )
        evidence_repo.upsert_schema_snapshot(
            {
                "snapshot_ref": "schema-res-1-v1",
                "resource_code": "res-legal-person",
                "binding_code": "bind-table-1",
                "schema_json": {"columns": ["credit_code"], "secret": "should-not-persist"},
                "source_ref": "dsp-metadata3:meta_baseinfo:meta-1",
            }
        )
        evidence_repo.upsert_schema_mapping(
            {
                "mapping_code": "map-credit-code",
                "catalog_code": "cat-legal-person",
                "catalog_item_code": "credit_code",
                "resource_code": "res-legal-person",
                "binding_code": "bind-table-1",
                "source_schema_ref": {"table": "t_legal_person", "column": "credit_code", "password": "should-not-persist"},
                "mapping_rule_json": {"method": "direct", "secret": "should-not-persist"},
                "confidence_level": "confirmed",
                "evidence_ref": "schema-res-1-v1",
                "source_ref": "dsp-metadata3:rc_resource_catalog_item_link:link-1",
                "legacy_object_ref": "link-1",
            }
        )
        evidence_repo.upsert_gather_evidence(
            {
                "gather_task_ref": "gather-1",
                "resource_code": "res-legal-person",
                "schema_snapshot_ref": "schema-res-1-v1",
                "status": "succeeded",
                "evidence_json": {"rows": 2, "secret": "should-not-persist"},
            }
        )
        evidence_repo.upsert_lineage_relation(
            {
                "relation_ref": "lineage-1",
                "relation_scope": "column",
                "source_resource_code": "res-source",
                "source_schema_ref": "source.credit_code",
                "target_resource_code": "res-legal-person",
                "target_schema_ref": "target.credit_code",
                "relation_type": "etl",
                "relation_rule_json": {"expr": "direct", "secret": "should-not-persist"},
            }
        )
        evidence_repo.upsert_quality_evidence(
            {
                "quality_ref": "quality-1",
                "target_type": "catalog_item",
                "target_ref": "credit_code",
                "quality_status": "passed",
                "score": 96,
                "evidence_json": {"missing": 0, "secret": "should-not-persist"},
            }
        )

        assert catalog_repo.list_models()[0].model_schema_json == {"fields": ["name", "credit_code"]}
        assert catalog_repo.list_model_fields("legal-person-base")[0].field_policy_json == {"share_condition": "审批后共享"}
        assert catalog_repo.list_entry_versions("cat-legal-person")[0].snapshot_json == {"items": ["credit_code"]}
        assert evidence_repo.list_schema_mappings(resource_code="res-legal-person")[0].source_schema_ref == {"table": "t_legal_person", "column": "credit_code"}
        mappings = LegacyObjectMappingRepository().list_mappings(canonical_type="resource_schema_mapping")
        assert any(item.legacy_object_ref == "link-1" for item in mappings)


def test_runtime_sync_writes_aggregate_tables() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "repo.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from sqlalchemy import create_engine, text
        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared import audit as audit_bus
        from zw_brain.shared.state_store import StateStore
        from zw_brain.command.brain import BrainService

        ensure_runtime_schema()
        store = DatabaseStore()
        audit_bus.configure_sink(store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=store))
        service.invoke_skill("approval.review_decide", {"request_id": "REQ-2026-04-25-0011", "decision": "approve", "role": "r2", "confirmed": True})
        store.sync_aggregate_tables(service.snapshot())

        engine = create_engine(f"sqlite:///{db_path}", future=True)
        with engine.connect() as conn:
            assert conn.execute(text("select count(*) from catalog_entry")).scalar_one() > 0
            assert conn.execute(text("select count(*) from catalog_item")).scalar_one() > 0
            assert conn.execute(text("select count(*) from application_record")).scalar_one() > 0
            assert conn.execute(text("select count(*) from approval_case")).scalar_one() > 0
            assert conn.execute(text("select count(*) from approval_step")).scalar_one() > 0
            assert conn.execute(text("select count(*) from approval_decision")).scalar_one() > 0
            assert conn.execute(text("select count(*) from delivery_task")).scalar_one() > 0
            assert conn.execute(text("select count(*) from delivery_receipt")).scalar_one() > 0
            assert conn.execute(text("select count(*) from capability_package")).scalar_one() > 0
            assert conn.execute(text("select count(*) from tenant_capability_policy")).scalar_one() > 0


def test_tenant_capability_disable_does_not_change_package_review_status() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "repo.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.domain.repositories.capability_package import CapabilityPackageRepository

        ensure_runtime_schema()
        repo = CapabilityPackageRepository()
        package = {
            "slug": "pkg-formal-test",
            "status": "approved",
            "source": "registry",
            "exposure": ["webui", "mcp"],
            "requiresHuman": True,
            "auditClass": "high",
            "tenantPolicy": {"maxDailyCalls": 10},
        }
        repo.upsert_from_package(package)

        policy = repo.set_tenant_policy_status(package, policy_status="disabled", enabled=False, exposed_surfaces=[])
        stored = next(item for item in repo.list_packages() if item.package_slug == "pkg-formal-test")

        assert stored.review_status == "approved"
        assert policy.policy_status == "disabled"
        assert policy.policy_json["enabled"] is False
        assert policy.policy_json["exposedSurfaces"] == []


def test_greenfield_schema_contains_step_receipt_and_policy_tables() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "repo.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from sqlalchemy import create_engine, inspect
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        with engine.connect() as conn:
            tables = set(inspect(conn).get_table_names())
            assert "resource_api_test_projection" in tables
            assert "catalog_item" in tables
            columns = {column["name"] for column in inspect(conn).get_columns("resource_asset")}
            assert {"owner_org_snapshot_json", "region_code", "access_policy_json", "qos_policy_json"}.issubset(columns)
            binding_columns = {column["name"] for column in inspect(conn).get_columns("resource_channel_binding")}
            assert {"endpoint_ref", "schema_ref"}.issubset(binding_columns)
            metric_columns = {column["name"] for column in inspect(conn).get_columns("service_invocation_metric_projection")}
            assert {"provider_region_code", "consumer_region_code", "bucket_granularity", "provider_error_count", "consumer_error_count", "gateway_error_count", "other_error_count", "apply_count", "p95_latency_ms", "last_error_code", "last_error_at"}.issubset(metric_columns)


def test_governance_schema_and_projection_are_persisted() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "repo.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from sqlalchemy import create_engine, text
        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared import audit as audit_bus
        from zw_brain.shared.state_store import StateStore
        from zw_brain.command.brain import BrainService

        ensure_runtime_schema()
        store = DatabaseStore()
        audit_bus.configure_sink(store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=store))
        store.sync_aggregate_tables(service.snapshot())

        engine = create_engine(f"sqlite:///{db_path}", future=True)
        with engine.connect() as conn:
            assert conn.execute(text("select count(*) from objection_case")).scalar_one() > 0
            assert conn.execute(text("select count(*) from objection_evidence")).scalar_one() > 0
            assert conn.execute(text("select count(*) from objection_process")).scalar_one() > 0
            assert conn.execute(text("select count(*) from objection_evaluation")).scalar_one() > 0


def test_external_adapter_repository_idempotency_and_secret_sanitization() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "repo.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.domain.repositories.external_adapter import ExternalAdapterRepository

        ensure_runtime_schema()
        repo = ExternalAdapterRepository()
        first = repo.upsert_run_record(
            {
                "adapter_slug": "national",
                "operation": "receive",
                "direction": "inbound",
                "idempotency_key": "idem-1",
                "status": "succeeded",
                "receipt_json": {"token": "should-not-persist", "receipt_no": "R1"},
            }
        )
        second = repo.upsert_run_record(
            {
                "adapter_slug": "national",
                "operation": "receive",
                "direction": "inbound",
                "idempotency_key": "idem-1",
                "status": "failed",
                "error_summary": "remote rejected",
                "receipt_json": {"api_key": "should-not-persist", "receipt_no": "R2"},
            }
        )
        assert first.id == second.id
        assert second.status == "failed"
        assert second.receipt_json == {"receipt_no": "R2"}

        mapping = repo.upsert_mapping(
            {
                "external_system": "national_platform",
                "direction": "inbound",
                "local_aggregate_type": "application",
                "local_aggregate_id": "REQ-1",
                "external_object_type": "national_application",
                "external_object_id": "NAT-1",
                "last_receipt_json": {"certificate": "should-not-persist", "status": "accepted"},
                "extra_json": {"private_key": "should-not-persist", "batch": "B1"},
            }
        )
        assert mapping.last_receipt_json == {"status": "accepted"}
        assert mapping.extra_json == {"batch": "B1"}
        assert repo.list_mappings(local_aggregate_id="REQ-1")[0].id == mapping.id




def test_p1_governance_projection_and_topic_package_repositories() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "repo.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
        from zw_brain.domain.repositories.topic_package import TopicPackageRepository, TopicPackageStateError

        ensure_runtime_schema()
        governance = GovernanceProjectionRepository()
        governance.upsert_org({"org_code": "ORG-1", "org_name": "区政数局", "profile_json": {"secret": "drop", "level": "district"}})
        governance.upsert_actor({"external_actor_id": "u-1", "display_name": "治理员", "org_code": "ORG-1", "role_codes": ["r7"], "profile_json": {"token": "drop", "mobile_mask": "138****0000"}})
        candidate = governance.import_legacy_policy_candidate({"legacy_permission_ref": "bsp:menu:sharezone", "legacy_role_ref": "ROLE_ADMIN", "capability_id": "topic.package.publish", "surface": "webui", "evidence_json": {"password": "drop", "source": "dsp-bsp"}})
        assert governance.list_orgs()[0].profile_json == {"level": "district"}
        assert governance.list_actors()[0].profile_json == {"mobile_mask": "138****0000"}
        assert candidate.evidence_json == {"source": "dsp-bsp"}

        topic = TopicPackageRepository()
        topic.create_package({"package_code": "tp-ybt", "title": "一表通减负专题", "display_snapshot_json": {"secret": "drop", "hero": "基层只补差异"}})
        topic.configure_package(
            "tp-ybt",
            {
                "items": [{"item_code": "cat-jbxx", "ref_type": "catalog", "ref_id": "cat-jbxx", "summary_json": {"token": "drop", "domain": "法人"}}],
                "visibility": [{"visibility_code": "r7-web", "role_code": "r7", "policy_status": "approved", "condition_json": {"api_key": "drop", "intent": "publish"}}],
            },
        )
        topic.transition_package("tp-ybt", "submitted", {"opinion": "提交审核"})
        published = topic.transition_package("tp-ybt", "published", {"action_type": "review", "opinion": "通过"})
        topic.attach_evidence("tp-ybt", {"evidence_type": "case", "title": "基层减负案例", "content_json": {"certificate": "drop", "saving": 3}})
        topic.upsert_metric("tp-ybt", {"metric_key": "reuse_count", "metric_value": 8, "metric_json": {"private_key": "drop", "unit": "org"}})

        assert published.status == "published"
        assert topic.list_items("tp-ybt")[0].summary_json == {"domain": "法人"}
        assert topic.list_visibility("tp-ybt")[0].condition_json == {"intent": "publish"}
        assert topic.list_evidence("tp-ybt")[0].content_json == {"saving": 3}
        assert topic.list_metrics("tp-ybt")[0].metric_json == {"unit": "org"}

        topic.create_package({"package_code": "tp-blocked", "title": "未满足发布条件"})
        topic.transition_package("tp-blocked", "submitted", {})
        try:
            topic.transition_package("tp-blocked", "published", {})
        except TopicPackageStateError:
            pass
        else:
            raise AssertionError("topic package without item and approved visibility must not publish")


def test_compliance_ops_repository_six_records_roundtrip() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "repo.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from datetime import UTC, datetime

        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.domain.repositories.compliance_ops import ComplianceOpsRepository

        ensure_runtime_schema()
        repo = ComplianceOpsRepository()
        tenant = "sd-default"

        case = repo.upsert_case(
            {
                "case_code": "CASE-2026-0001",
                "case_kind": "timeout",
                "target_type": "application",
                "target_ref": "APP-001",
                "severity": "high",
                "detected_summary": "申请审批超期 3 天",
                "evidence_json": {"secret": "drop", "rule_ref": "RULE-TO-1"},
                "source_ref": "dsp-esupervision:apply/timeLimitHandle",
            },
            tenant_id=tenant,
        )
        assert case.status == "detected" and case.evidence_json == {"rule_ref": "RULE-TO-1"}

        rule = repo.upsert_rule(
            {
                "rule_code": "RULE-TO-1",
                "rule_kind": "timeout",
                "target_scope": "application",
                "title": "申请审批超期阈值",
                "threshold_json": {"days": 3, "private_key": "drop"},
            },
            tenant_id=tenant,
        )
        assert rule.review_status == "pending_review" and rule.threshold_json == {"days": 3}

        risk = repo.upsert_risk_event(
            {
                "event_kind": "abnormal",
                "severity": "high",
                "source_system": "dsp-monitor",
                "source_ref": "warning:abc-1",
                "target_type": "delivery",
                "target_ref": "DLV-9",
                "detected_at": datetime.now(UTC),
                "summary_json": {"token": "drop", "rate": 0.42},
            },
            tenant_id=tenant,
        )
        assert risk.summary_json == {"rate": 0.42}

        health = repo.upsert_health_signal(
            {
                "subject_kind": "service",
                "subject_ref": "api-service-info:63",
                "status": "degraded",
                "metric_json": {"password": "drop", "p99_ms": 820},
            },
            tenant_id=tenant,
        )
        assert health.metric_json == {"p99_ms": 820}

        asset = repo.upsert_standard_asset(
            {
                "asset_kind": "element",
                "asset_ref": "elem:GB/T-XXXX-2014",
                "title": "公民身份号码",
                "source_system": "standardservice",
                "evidence_json": {"api_key": "drop", "version": "2014"},
            },
            tenant_id=tenant,
        )
        assert asset.status == "candidate" and asset.evidence_json == {"version": "2014"}

        metric = repo.upsert_metric_definition(
            {
                "metric_code": "metric.application.timeout.rate",
                "title": "申请超期率",
                "metric_kind": "rate",
                "target_aggregate": "ApplicationRecord",
                "dimension_json": {"certificate": "drop", "by": "owner_org"},
            },
            tenant_id=tenant,
        )
        assert metric.dimension_json == {"by": "owner_org"}

        # idempotent upsert (same UNIQUE keys returns single row)
        repo.upsert_case({**{"case_code": "CASE-2026-0001"}, "status": "acknowledged", "detected_summary": case.detected_summary, "target_type": case.target_type, "target_ref": case.target_ref}, tenant_id=tenant)
        cases = repo.list_cases(tenant_id=tenant)
        assert len(cases) == 1 and cases[0].status == "acknowledged"

        assert len(repo.list_rules(tenant_id=tenant)) == 1
        assert len(repo.list_risk_events(tenant_id=tenant)) == 1
        assert len(repo.list_health_signals(tenant_id=tenant)) == 1
        assert len(repo.list_standard_assets(tenant_id=tenant)) == 1
        assert len(repo.list_metric_definitions(tenant_id=tenant)) == 1
