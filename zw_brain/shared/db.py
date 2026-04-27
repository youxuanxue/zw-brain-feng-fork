from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / ".data" / "zw_brain.db"


class Base(DeclarativeBase):
    pass


def get_database_url() -> str:
    db_path = Path(os.environ.get("ZW_BRAIN_DB_PATH", DEFAULT_DB_PATH))
    return os.environ.get("ZW_BRAIN_DATABASE_URL", f"sqlite:///{db_path}")


def create_session_factory() -> sessionmaker[Session]:
    engine = create_engine(get_database_url(), future=True)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def ensure_parent_dir() -> None:
    if get_database_url().startswith("sqlite:///"):
        Path(get_database_url().removeprefix("sqlite:///")) .parent.mkdir(parents=True, exist_ok=True)
