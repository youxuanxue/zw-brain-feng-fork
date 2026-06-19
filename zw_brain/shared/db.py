from __future__ import annotations

import os
import threading

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Default runtime backend = local PostgreSQL (psycopg v3). Credentials/port match
# docker-compose.yml so `docker compose up -d postgres` + bare start-local.sh
# connect with zero env config. Override the whole URL via ZW_BRAIN_DATABASE_URL
# (single knob; tests/CI point this at a per-test PG database).
DEFAULT_PG_URL = "postgresql+psycopg://zw_brain:zw_brain@127.0.0.1:5432/zw_brain"


class Base(DeclarativeBase):
    pass


def get_database_url() -> str:
    # ZW_BRAIN_DB_PATH was the legacy SQLite file knob — permanently retired by the
    # full-PG migration. Setting it now is a stale SQLite assumption; rather than
    # silently ignore it (and route the caller to PG while they think they're on a
    # file DB), fail closed so the mistake surfaces immediately.
    if os.environ.get("ZW_BRAIN_DB_PATH"):
        raise RuntimeError(
            "ZW_BRAIN_DB_PATH is no longer supported — 全盘 PG 迁移已删 SQLite 分支。"
            "用 ZW_BRAIN_DATABASE_URL 指向 PostgreSQL（postgresql+psycopg://…）。"
        )
    # ① explicit URL wins — tests/CI/demos that need a specific PG database.
    url = os.environ.get("ZW_BRAIN_DATABASE_URL")
    if not url:
        # ② no env → default to local PostgreSQL (see DEFAULT_PG_URL).
        url = DEFAULT_PG_URL
    # SQLite is permanently retired (full-PG migration). A sqlite URL — whether
    # injected via env or a stale default — would silently route writes off the
    # PG-only audit/runtime path, so fail closed rather than degrade.
    if make_url(url).get_backend_name() == "sqlite":
        raise RuntimeError(
            "SQLite is no longer supported — ZW_BRAIN_DATABASE_URL must name a "
            "PostgreSQL database (postgresql+psycopg://…). 全盘 PG 迁移已删 SQLite 分支。"
        )
    return url


# Engine cache: 1 engine + 1 sessionmaker per (url) — creating a new engine on
# every repository method made audit.list / compliance.case.query
# take ~30-77 seconds because each call spun up a fresh connection pool. With
# the cache, the same sessionmaker is reused, sub-second hot path restored.
_ENGINE_CACHE: dict[str, tuple[Engine, sessionmaker[Session]]] = {}
_CACHE_LOCK = threading.Lock()


def _build_engine(url: str) -> Engine:
    # pool_pre_ping handles stale connections (server restart, idle timeout).
    return create_engine(url, future=True, pool_pre_ping=True)


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
    audit.list / compliance.case.query for tens of seconds.
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
    """No-op under PostgreSQL.

    Historically created the parent directory for a SQLite file before opening
    it. The runtime is PG-only now — the server owns its storage and there is no
    local file to pre-create. Kept as a no-op so existing call sites
    (database_store / migration_batch / seed fixtures) need no change.
    """
    return None
