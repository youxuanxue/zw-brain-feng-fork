"""Process-wide runtime singletons."""
from __future__ import annotations

from sqlalchemy import create_engine

from zw_brain.command.brain import BrainService
from zw_brain.domain.models import Base
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.db import get_database_url
from zw_brain.shared.migrate import ensure_runtime_schema
from zw_brain.shared.state_store import StateStore

_service: BrainService | None = None


def get_service() -> BrainService:
    global _service
    if _service is None:
        database_store = DatabaseStore()
        database_store.initialize()
        ensure_runtime_schema()
        engine = create_engine(get_database_url(), future=True)
        Base.metadata.create_all(bind=engine)
        _service = BrainService(state_store=StateStore(database_store=database_store))
        database_store.replace_capability_manifests(_service.manifests())
        database_store.sync_aggregate_tables(_service.snapshot())
    return _service
