from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from zw_brain.shared.db import get_database_url

REQUIRED_TABLES = {
    "runtime_state",
    "audit_event",
    "anchor_outbox",
    "capability_manifest",
    "catalog_entry",
    "application_record",
    "approval_case",
    "approval_step",
    "approval_decision",
    "delivery_task",
    "objection_case",
    "objection_evidence",
    "objection_process",
    "objection_evaluation",
    "tenant_capability_policy",
}
REQUIRED_COLUMNS = {
    "approval_step": {"decision_mode", "started_at", "completed_at"},
    "approval_decision": {"decision_reason"},
    "delivery_receipt": {"receipt_no", "acknowledged_at"},
}


def _assets_root() -> Path:
    package_root = Path(__file__).resolve().parents[1]
    packaged = package_root / "_assets"
    if packaged.exists():
        return packaged
    return package_root.parents[0]


def _alembic_ini() -> Path:
    return _assets_root() / "alembic.ini"


def _alembic_script_location() -> Path:
    return _assets_root() / "alembic"


def _config() -> Config:
    cfg = Config(str(_alembic_ini()))
    cfg.set_main_option("script_location", str(_alembic_script_location()))
    cfg.set_main_option("sqlalchemy.url", get_database_url())
    return cfg


def upgrade() -> None:
    command.upgrade(_config(), "head")


def reset_and_upgrade() -> None:
    engine = create_engine(get_database_url(), future=True)
    with engine.begin() as conn:
        inspector = inspect(conn)
        for table_name in inspector.get_table_names():
            conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
    upgrade()


def ensure_runtime_schema() -> None:
    engine = create_engine(get_database_url(), future=True)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if not REQUIRED_TABLES.issubset(tables):
        reset_and_upgrade()
        return
    for table_name, required_columns in REQUIRED_COLUMNS.items():
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if not required_columns.issubset(columns):
            reset_and_upgrade()
            return
