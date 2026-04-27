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

        ensure_runtime_schema()
        repo = CatalogRepository()
        resource = {
            "id": "res-demo",
            "name": "示例目录模板",
            "status": "published",
            "provider": "区政数局",
        }
        repo.upsert_from_resource(resource)
        records = repo.list_entries()
        assert any(item.catalog_code == "res-demo" for item in records)


def test_runtime_sync_writes_aggregate_tables() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "repo.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from sqlalchemy import create_engine, text
        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.state_store import StateStore
        from zw_brain.command.brain import BrainService

        ensure_runtime_schema()
        store = DatabaseStore()
        service = BrainService(state_store=StateStore(database_store=store))
        service.invoke_skill("approval.review_decide", {"request_id": "REQ-2026-04-25-0011", "decision": "approve", "role": "r2", "confirmed": True})
        store.sync_aggregate_tables(service.snapshot())

        engine = create_engine(f"sqlite:///{db_path}", future=True)
        with engine.connect() as conn:
            assert conn.execute(text("select count(*) from catalog_entry")).scalar_one() > 0
            assert conn.execute(text("select count(*) from application_record")).scalar_one() > 0
            assert conn.execute(text("select count(*) from approval_case")).scalar_one() > 0
            assert conn.execute(text("select count(*) from approval_step")).scalar_one() > 0
            assert conn.execute(text("select count(*) from approval_decision")).scalar_one() > 0
            assert conn.execute(text("select count(*) from delivery_task")).scalar_one() > 0
            assert conn.execute(text("select count(*) from delivery_receipt")).scalar_one() > 0
            assert conn.execute(text("select count(*) from capability_package")).scalar_one() > 0
            assert conn.execute(text("select count(*) from tenant_capability_policy")).scalar_one() > 0


def test_greenfield_schema_contains_step_receipt_and_policy_tables() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "repo.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from sqlalchemy import create_engine, inspect
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        engine = create_engine(f"sqlite:///{db_path}", future=True)


def test_governance_schema_and_projection_are_persisted() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "repo.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from sqlalchemy import create_engine, text
        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.state_store import StateStore
        from zw_brain.command.brain import BrainService

        ensure_runtime_schema()
        store = DatabaseStore()
        service = BrainService(state_store=StateStore(database_store=store))
        store.sync_aggregate_tables(service.snapshot())

        engine = create_engine(f"sqlite:///{db_path}", future=True)
        with engine.connect() as conn:
            assert conn.execute(text("select count(*) from objection_case")).scalar_one() > 0
            assert conn.execute(text("select count(*) from objection_evidence")).scalar_one() > 0
            assert conn.execute(text("select count(*) from objection_process")).scalar_one() > 0
            assert conn.execute(text("select count(*) from objection_evaluation")).scalar_one() > 0
