from __future__ import annotations

import os
import threading
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / ".data" / "zw_brain.db"


class Base(DeclarativeBase):
    pass


def get_database_url() -> str:
    db_path = Path(os.environ.get("ZW_BRAIN_DB_PATH", DEFAULT_DB_PATH))
    return os.environ.get("ZW_BRAIN_DATABASE_URL", f"sqlite:///{db_path}")


# Engine cache: 1 engine + 1 sessionmaker per (url) — creating a new engine on
# every repository method made audit.list / dashboard.render_command_center
# take ~30-77 seconds because each call spun up a fresh connection pool. With
# the cache, the same sessionmaker is reused, sub-second hot path restored.
_ENGINE_CACHE: dict[str, tuple[Engine, sessionmaker[Session]]] = {}
_CACHE_LOCK = threading.Lock()


def _build_engine(url: str) -> Engine:
    # check_same_thread=False is safe under sessionmaker (sessions don't share
    # connections across threads). pool_pre_ping handles stale connections.
    connect_args: dict[str, object] = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine = create_engine(url, future=True, pool_pre_ping=True, connect_args=connect_args)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _sqlite_tune(dbapi_conn, _record):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            try:
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA busy_timeout=10000")
                cur.execute("PRAGMA synchronous=NORMAL")
                cur.execute("PRAGMA foreign_keys=ON")
            finally:
                cur.close()
    return engine


def _get_cached(url: str) -> sessionmaker[Session]:
    entry = _ENGINE_CACHE.get(url)
    if entry is not None:
        return entry[1]
    with _CACHE_LOCK:
        entry = _ENGINE_CACHE.get(url)
        if entry is not None:
            return entry[1]
        engine = _build_engine(url)
        factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
        _ENGINE_CACHE[url] = (engine, factory)
        return factory


def create_session_factory() -> sessionmaker[Session]:
    """Return a cached sessionmaker (1 per DB URL). Engine creation is
    expensive; callers used to pay it on every repository method, blocking
    audit.list / dashboard.render_command_center for tens of seconds.
    """
    return _get_cached(get_database_url())


def reset_engine_cache() -> None:
    """Test hook: drop all cached engines (e.g. after switching DB URL)."""
    with _CACHE_LOCK:
        for engine, _ in _ENGINE_CACHE.values():
            try:
                engine.dispose()
            except Exception:  # noqa: BLE001
                pass
        _ENGINE_CACHE.clear()


def ensure_parent_dir() -> None:
    if get_database_url().startswith("sqlite:///"):
        Path(get_database_url().removeprefix("sqlite:///")) .parent.mkdir(parents=True, exist_ok=True)
