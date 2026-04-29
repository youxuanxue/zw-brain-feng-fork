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
            "anchor_outbox",
            "capability_manifest",
            "catalog_entry",
            "resource_asset",
            "resource_channel_binding",
            "gateway_runtime_status_projection",
            "service_invocation_metric_projection",
            "application_record",
            "approval_case",
            "approval_step",
            "approval_decision",
            "delivery_task",
            "delivery_receipt",
            "capability_package",
            "tenant_capability_policy",
        }.issubset(tables)


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
            assert conn.execute(text("select count(*) from anchor_outbox")).scalar_one() >= 1


def test_database_store_lists_pending_anchor_outbox() -> None:
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
