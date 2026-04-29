from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory


def test_background_worker_processes_durable_outbox() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        import os
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)

        from sqlalchemy import create_engine, text
        from zw_brain.shared.migrate import ensure_runtime_schema
        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.background_tasks import run_once

        ensure_runtime_schema()
        store = DatabaseStore()
        store.append_anchor_outbox("REQ-1", "approval.review_decide", "hash-durable", "mock-chain")

        processed = asyncio.run(run_once())
        assert processed >= 1

        engine = create_engine(f"sqlite:///{db_path}", future=True)
        with engine.connect() as conn:
            delivered = conn.execute(text("select delivered from anchor_outbox where content_hash = 'hash-durable'"))
            assert delivered.scalar_one() == 1
            receipt = conn.execute(text("select tx_hash from audit_receipt where content_hash = 'hash-durable'"))
            assert receipt.scalar_one() == "mock:hash-durable"
