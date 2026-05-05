from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory


def test_database_store_persists_runtime_state() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.database_store import DatabaseStore
        from sqlalchemy import create_engine, inspect

        ensure_runtime_schema()
        store = DatabaseStore()
        snapshot, ui_state = store.load_runtime_state()
        assert "requests" in snapshot
        ui_state["role"] = "r6"
        store.save_runtime_state(snapshot, ui_state)
        loaded_snapshot, loaded_ui = store.load_runtime_state()
        assert "requests" in loaded_snapshot
        assert loaded_ui["role"] == "r6"

        engine = create_engine(f"sqlite:///{db_path}", future=True)
        tables = set(inspect(engine).get_table_names())
        assert {
            "runtime_state",
            "audit_event",
            "capability_call",
            "anchor_outbox",
            "audit_receipt",
            "capability_manifest",
            "catalog_entry",
            "catalog_item",
            "resource_asset",
            "resource_channel_binding",
            "gateway_runtime_status_projection",
            "service_invocation_metric_projection",
            "legacy_object_mapping",
            "application_record",
            "approval_case",
            "approval_step",
            "approval_decision",
            "delivery_task",
            "delivery_receipt",
            "capability_package",
            "tenant_capability_policy",
            "objection_case",
            "objection_evidence",
            "objection_process",
            "objection_evaluation",
            "external_object_mapping",
            "adapter_run_record",
            "tenant_projection",
            "org_projection",
            "region_projection",
            "role_projection",
            "actor_projection",
            "legacy_policy_mapping_candidate",
            "topic_package",
            "topic_package_item",
            "topic_package_visibility",
            "topic_package_review_record",
            "topic_package_evidence",
            "topic_package_metric_projection",
            "delivery_subscription",
            "delivery_attempt",
            "delivery_execution_evidence",
            "exchange_metric_projection",
        }.issubset(tables)
        assert {"runtime_profile"}.issubset({column["name"] for column in inspect(engine).get_columns("gateway_runtime_status_projection")})
        assert {"failed_count"}.issubset({column["name"] for column in inspect(engine).get_columns("service_invocation_metric_projection")})


def test_runtime_schema_guard_columns_are_subset_of_required_tables() -> None:
    from zw_brain.shared.migrate import REQUIRED_COLUMNS, REQUIRED_TABLES

    assert set(REQUIRED_COLUMNS).issubset(REQUIRED_TABLES)


def test_runtime_service_uses_database_backing() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.command.brain import BrainService
        from zw_brain.shared import audit as audit_bus
        from zw_brain.shared.state_store import StateStore
        from sqlalchemy import create_engine, text

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))
        service.invoke_skill("approval.review_decide", {"request_id": "REQ-2026-04-25-0011", "decision": "approve", "role": "r2", "confirmed": True})
        snapshot, _ = database_store.load_runtime_state()
        request = next(item for item in snapshot["requests"] if item["id"] == "REQ-2026-04-25-0011")
        assert request["status"] == "supplementing"

        engine = create_engine(f"sqlite:///{db_path}", future=True)
        with engine.connect() as conn:
            assert conn.execute(text("select count(*) from application_record")).scalar_one() > 0
            assert conn.execute(text("select count(*) from approval_case")).scalar_one() > 0
            assert conn.execute(text("select count(*) from approval_step")).scalar_one() > 0
            assert conn.execute(text("select count(*) from approval_decision")).scalar_one() > 0
            assert conn.execute(text("select count(*) from delivery_task")).scalar_one() > 0
            assert conn.execute(text("select count(*) from delivery_receipt")).scalar_one() > 0
            assert conn.execute(text("select count(*) from catalog_entry")).scalar_one() > 0
            assert conn.execute(text("select count(*) from audit_event")).scalar_one() >= 2
            assert conn.execute(text("select count(*) from capability_call")).scalar_one() >= 1
            assert conn.execute(text("select count(*) from anchor_outbox")).scalar_one() >= 1


def test_database_store_records_capability_calls_and_tenant_policy_decisions() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.command.brain import BrainService
        from zw_brain.shared import audit as audit_bus
        from zw_brain.shared.state_store import StateStore

        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))
        service.invoke_skill("package.review_decide", {"package_id": "PKG-2026-04-25-001", "decision": "approve", "role": "r7", "confirmed": True})
        service.invoke_skill("package.register_version", {"package_id": "PKG-2026-04-25-001", "role": "r7", "confirmed": True})
        service.invoke_skill("package.apply_tenant_policy", {"package_id": "PKG-2026-04-25-001", "role": "r7", "confirmed": True})

        decision = service.invoke_skill("tenant.policy.evaluate", {"capability_id": "ledger.entity.base.read", "surface": "api", "role": "r7"})
        blocked = service.invoke_skill("tenant.policy.evaluate", {"capability_id": "ledger.entity.base.read", "surface": "webui", "role": "r7"})
        service.invoke_skill("request.view", {"request_id": "REQ-2026-04-25-0011", "role": "r2"})
        calls = database_store.list_capability_calls()

        assert decision["source"] == "tenant_capability_policy"
        assert decision["allowed"] is True
        assert blocked["source"] == "tenant_capability_policy"
        assert blocked["allowed"] is False
        assert any(item.skill_id == "package.apply_tenant_policy" and item.status == "succeeded" for item in calls)
        assert any(item.skill_id == "tenant.policy.evaluate" and item.output_json["source"] == "tenant_capability_policy" for item in calls)
        assert any(item.skill_id == "request.view" and item.input_json["request_id"] == "REQ-2026-04-25-0011" for item in calls)
        assert any(item.input_json.get("package_id") == "PKG-2026-04-25-001" for item in calls)

    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.database_store import DatabaseStore

        ensure_runtime_schema()
        store = DatabaseStore()
        store.append_anchor_outbox("REQ-1", "approval.review_decide", "hash-1", "mock-chain")
        store.append_anchor_outbox("REQ-2", "summary.confirm", "hash-2", "mock-chain")

        pending = store.list_pending_anchor_outbox()
        hashes = [item.content_hash for item in pending]
        assert hashes == ["hash-1", "hash-2"]

        store.mark_anchor_delivered("hash-1")
        remaining = store.list_pending_anchor_outbox()
        assert [item.content_hash for item in remaining] == ["hash-2"]


def test_legacy_mapping_marks_conflicts_without_overwrite() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.database_store import DatabaseStore

        ensure_runtime_schema()
        store = DatabaseStore()
        store.legacy_mapping_repo.upsert_mapping(
            {
                "source_ref": "dsp-dataservice:api_service_info:legacy-1",
                "legacy_object_ref": "legacy-1",
                "canonical_type": "resource_asset",
                "canonical_ref": "api-one",
            }
        )
        store.legacy_mapping_repo.upsert_mapping(
            {
                "source_ref": "dsp-dataservice:api_service_info:legacy-1",
                "legacy_object_ref": "legacy-1",
                "canonical_type": "resource_asset",
                "canonical_ref": "api-two",
            }
        )

        mappings = store.legacy_mapping_repo.list_mappings(canonical_type="resource_asset")
        assert {item.canonical_ref for item in mappings} == {"api-one", "api-two"}
        assert {item.mapping_status for item in mappings} == {"conflicted"}
