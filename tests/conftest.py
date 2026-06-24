"""Root pytest conftest — central PostgreSQL test-DB supply + per-test isolation.

WHY THIS EXISTS
---------------
The runtime is PostgreSQL-only (``zw_brain.shared.db`` resolves
``ZW_BRAIN_DATABASE_URL`` → ``DEFAULT_PG_URL``; there is no SQLite branch). Every
test therefore needs a *real* PG database, and tests must not see each other's
rows. Two historical hazards make naive sharing flaky:

1. **A shared default DB accumulates rows.** ~96 test modules drive the DB purely
   through env vars (``ZW_BRAIN_DATABASE_URL`` / the now-inert ``ZW_BRAIN_DB_PATH``)
   and expect a clean, seedable database. If they all fell through to one
   ``DEFAULT_PG_URL`` database, writes from one test would leak into the next and
   "assert empty" tests would fail order-dependently.
2. **Process-wide caches pin a connection.** ``zw_brain.shared.db._ENGINE_CACHE``
   holds a live SQLAlchemy engine keyed by URL, and ``audit.store._default_store``
   holds an open raw-``psycopg`` connection keyed by the DSN at creation time. A
   leaked/stale entry can serve a later test a connection to the wrong (or, under
   per-test DROP DATABASE, a *vanished*) database.

WHAT THIS DOES
--------------
* **Session scope — one migrated template DB.** ``_pg_template`` connects to the
  PG *server* named by ``ZW_BRAIN_DATABASE_URL`` (or ``DEFAULT_PG_URL`` for bare
  local runs), creates ``zw_tmpl_<uuid>``, and runs ``ensure_runtime_schema()``
  once (alembic upgrade head → all ORM tables). ``CREATE DATABASE … TEMPLATE``
  then makes per-test clones near-instant — the PG-idiomatic fast path.
* **Function scope (autouse) — one clone per test.** ``_isolate_db_env`` clones
  the template into ``zw_test_<uuid>`` and points BOTH ``ZW_BRAIN_DATABASE_URL``
  and the module-level ``db.DEFAULT_PG_URL`` at it. Pointing the default too means
  tests that *pop* ``ZW_BRAIN_DATABASE_URL`` (expecting "the default DB") still
  land on their own isolated clone, never a shared mutation sink. After the test
  it resets the engine cache + audit globals (so no connection pins the clone),
  restores the env snapshot exactly, restores ``DEFAULT_PG_URL``, and DROPs the
  clone ``WITH (FORCE)``.

MAINTENANCE / SERVER CONNECTION (single optional knob)
------------------------------------------------------
``CREATE``/``DROP DATABASE`` cannot run inside a transaction and cannot target the
connected database, so clones are issued over an autocommit connection to a
maintenance database (default ``postgres``) on the same server. The server DSN is
reused from ``ZW_BRAIN_DATABASE_URL``; the only extra knob is the optional
``ZW_BRAIN_TEST_PG_MAINTENANCE_DB`` (a database *name*) for servers whose
maintenance DB is not ``postgres``. No new connection variables are invented.

DEFERRAL TO EXPLICIT, HIGHER-SCOPED DB PINNING
----------------------------------------------
The ~24 SEED_DB "shadow" modules manage their own seed+read against the resolved
default inside a module/session-scoped autouse fixture that sets
``ZW_BRAIN_DB_PATH`` *before* this function fixture runs (their migration off the
shadow pattern is owned by a separate slice). Redirecting their reads to a fresh
empty clone here would make their already-done module-scope seeding invisible.
So when ``ZW_BRAIN_DB_PATH`` is set at our setup time we treat it as an explicit
opt-out of central supply and only apply env/cache/audit hygiene — never the
clone redirect. Tests that set their *own* ``ZW_BRAIN_DATABASE_URL`` in a
function fixture run *after* this one and win naturally (we never re-assert after
yield, and the snapshot/restore puts the env back afterwards).

COMPOSITION & CONTRACTS PRESERVED
---------------------------------
* The function fixture is still named ``_isolate_db_env`` and still snapshots /
  restores ``os.environ`` and resets the engine cache around every test, so the
  regression lock in ``tests/test_conftest_db_env_isolation.py`` (naked env
  mutation undone; cache empty at test start) holds unchanged.
* ``tests/e2e/conftest.py`` is a plain config module (no fixtures); this composes
  with it without conflict.

This is purely test infrastructure: no Mocks, no assertion changes.
"""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from sqlalchemy.engine import URL, make_url

from tests._pg_admin import drop_database, maintenance_connect
from zw_brain.shared import audit as _audit_bus
from zw_brain.shared import db as _db
from zw_brain.shared.audit import store as _audit_store

# D58: reset_and_upgrade()（drop_all + alembic upgrade）在生产路径被 M5 fail-closed 闸在
# ZW_BRAIN_ALLOW_SCHEMA_RESET=1 之后（否则 raise SchemaResetForbiddenError）。测试整体就是
# "显式允许重置"的上下文（模板/克隆都是一次性库），故进程级开此 env。生产绝不设置该 env。
# 单测里要验「无 env → raise」的用例用 monkeypatch.delenv 在该测内移除即可（per-test 覆盖）。
os.environ.setdefault("ZW_BRAIN_ALLOW_SCHEMA_RESET", "1")

# Server DSN pointer (reused, not a new knob): names the PG server + credentials.
_SERVER_URL_ENV = "ZW_BRAIN_DATABASE_URL"
# Single optional override: the maintenance DB name used for CREATE/DROP DATABASE
# (env name only). Defaults to "postgres".
_MAINTENANCE_DB_ENV = "ZW_BRAIN_TEST_PG_MAINTENANCE_DB"


class _NullCtx:
    def __enter__(self) -> None:  # pragma: no cover - trivial fallback
        return None

    def __exit__(self, *_exc: object) -> bool:  # pragma: no cover
        return False


class NoDbAccessError(BaseException):
    """Raised when a ``no_db`` test attempts to reach PostgreSQL.

    This intentionally bypasses broad ``except Exception`` blocks in contract
    probes, so accidental DB access still fails the test instead of being
    swallowed as an expected runtime error.
    """


def _reset_engine_cache() -> None:
    """Drop every cached SQLAlchemy engine, disposing it to return pooled
    connections (so a per-test clone has no live connection blocking DROP).

    Prefers ``zw_brain.shared.db.reset_engine_cache`` (disposes under the cache
    lock) and falls back to a manual dispose+clear if that helper is ever
    renamed/removed, so isolation never silently degrades to a no-op.
    """
    reset = getattr(_db, "reset_engine_cache", None)
    if callable(reset):
        reset()
        return
    lock = getattr(_db, "_CACHE_LOCK", None)
    cache = getattr(_db, "_ENGINE_CACHE", None)
    if cache is None:
        return
    ctx = lock if lock is not None else _NullCtx()
    with ctx:
        for entry in list(cache.values()):
            engine = entry[0] if isinstance(entry, tuple) else entry
            dispose = getattr(engine, "dispose", None)
            if callable(dispose):
                try:
                    dispose()
                except Exception:  # noqa: BLE001 — best-effort cleanup
                    pass
        cache.clear()


def _reset_audit_globals() -> None:
    """Close the process-global audit store and clear the audit-bus sink.

    The audit store keeps an open raw-``psycopg`` connection bound to the DSN at
    creation time (kept out of the ORM engine cache by design — D4 decoupling).
    Under per-test DROP DATABASE that connection would pin a vanished clone, so
    it must be closed alongside the engine cache. ``set_default_store(None)``
    closes the prior store; ``clear_sink()`` detaches any sink wired by a test.
    Both are the module's documented public API.
    """
    closer = getattr(_audit_store, "set_default_store", None)
    if callable(closer):
        try:
            closer(None)
        except Exception:  # noqa: BLE001 — best-effort cleanup
            pass
    clear = getattr(_audit_bus, "clear_sink", None)
    if callable(clear):
        clear()
    # The cached BrainService wires the audit sink once, at build time
    # (runtime.get_service → audit_bus.configure_sink). If a prior test built it
    # and this fixture then cleared the sink, a stale cached service would invoke
    # with no sink → AuditWriteError (D4). Drop it so the next get_service()
    # rebuilds against this test's clone DB and reconfigures the sink — keeping
    # audit durable per test and order-independent.
    try:
        from zw_brain.command import runtime as _runtime

        _runtime._service = None
    except Exception:  # noqa: BLE001 — best-effort cleanup
        pass


def _configure_durable_test_sink() -> None:
    """Wire a durable audit sink for the test, mirroring runtime startup.

    Production always has a durable sink configured once get_service() builds the
    daemon, and security paths (e.g. the MCP trust-level reject in
    entry/mcp/server.py:_emit_mcp_reject_audit) emit audit assuming it — they
    reject *before* building the service. Without a sink those paths hit D4's
    fail-closed ``AuditWriteError``. Lazily build a DatabaseStore on first emit
    (it reads get_database_url() then → the test's clone), so the ~all tests that
    never emit pay nothing, and any test that does gets durable PG audit. If a
    test calls get_service() it overwrites this with the runtime multiplex sink —
    also durable, no conflict.
    """
    state: dict[str, object] = {}

    def _sink(request_id: str, actor: str, skill_id: str, phase: str, payload: dict) -> None:
        store = state.get("store")
        if store is None:
            from zw_brain.shared.database_store import DatabaseStore

            store = DatabaseStore()
            state["store"] = store
        store.append_audit_event(request_id, actor, skill_id, phase, payload)  # type: ignore[attr-defined]

    _audit_bus.configure_sink(_sink)


def _restore_env(snapshot: dict[str, str]) -> None:
    """Restore ``os.environ`` to exactly ``snapshot``.

    Removes keys added during the test, restores keys deleted during the test,
    and resets keys whose value changed.
    """
    current = set(os.environ.keys())
    saved = set(snapshot.keys())
    for added in current - saved:
        del os.environ[added]
    for key in saved:
        if os.environ.get(key) != snapshot[key]:
            os.environ[key] = snapshot[key]


def _server_url() -> URL:
    """SQLAlchemy URL for the PG *server* (from env pointer, else the default)."""
    raw = os.environ.get(_SERVER_URL_ENV) or _db.DEFAULT_PG_URL
    return make_url(raw)


def _forbid_db_access(*_args: object, **_kwargs: object) -> None:
    raise NoDbAccessError(
        "pytest no_db test attempted to access PostgreSQL. "
        "Remove @pytest.mark.no_db or use a DB-backed test fixture."
    )


def _patch_loaded_db_access_aliases(
    monkeypatch: pytest.MonkeyPatch,
    *,
    get_database_url: object,
    create_session_factory: object,
) -> None:
    """Fail-close direct imports such as ``from shared.db import get_database_url``.

    Some runtime modules bind DB helpers at import time. A no_db test that
    accidentally drives one of those paths must still fail locally instead of
    trying to open PostgreSQL through a stale function alias.
    """
    for module_name, module in tuple(sys.modules.items()):
        if module is None or not module_name.startswith("zw_brain."):
            continue
        namespace = getattr(module, "__dict__", None)
        if not namespace:
            continue
        if namespace.get("get_database_url") is get_database_url:
            monkeypatch.setattr(module, "get_database_url", _forbid_db_access)
        if namespace.get("create_session_factory") is create_session_factory:
            monkeypatch.setattr(module, "create_session_factory", _forbid_db_access)


@pytest.fixture(scope="session")
def _pg_template() -> tuple[str, URL, psycopg.Connection]:
    """Build one migrated template DB for the whole session; clone from it per
    test. Yields ``(template_name, server_url, maintenance_connection)``.
    """
    server_url = _server_url()
    template = f"zw_tmpl_{uuid.uuid4().hex}"
    maint = maintenance_connect(server_url)
    drop_database(maint, template)  # paranoia: never inherit a stale template
    maint.execute(f'CREATE DATABASE "{template}" OWNER "{server_url.username}"')

    # Migrate the template against itself, then dispose the engine so the
    # template carries no live connection (CREATE … TEMPLATE forbids that).
    saved_env = os.environ.get(_SERVER_URL_ENV)
    saved_default = _db.DEFAULT_PG_URL
    try:
        os.environ[_SERVER_URL_ENV] = server_url.set(database=template).render_as_string(hide_password=False)
        _db.DEFAULT_PG_URL = os.environ[_SERVER_URL_ENV]
        _reset_engine_cache()
        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
    finally:
        _reset_engine_cache()
        _reset_audit_globals()
        _db.DEFAULT_PG_URL = saved_default
        if saved_env is None:
            os.environ.pop(_SERVER_URL_ENV, None)
        else:
            os.environ[_SERVER_URL_ENV] = saved_env

    try:
        yield template, server_url, maint
    finally:
        drop_database(maint, template)
        maint.close()


@pytest.fixture(autouse=True)
def _isolate_db_env(request: pytest.FixtureRequest) -> Iterator[None]:
    """Autouse, function-scoped: per-test PG clone + env/cache/audit isolation.

    See the module docstring for the full rationale, the deferral contract for
    explicit ``ZW_BRAIN_DB_PATH`` pinning, and the composition guarantee with the
    isolation regression lock.
    """
    # A leaked engine/audit connection from a prior test must not bleed in.
    _reset_engine_cache()
    _reset_audit_globals()
    env_snapshot = dict(os.environ)

    if request.node.get_closest_marker("no_db"):
        monkeypatch: pytest.MonkeyPatch = request.getfixturevalue("monkeypatch")
        original_get_database_url = _db.get_database_url
        original_create_session_factory = _db.create_session_factory
        monkeypatch.setenv(
            _SERVER_URL_ENV,
            "postgresql+psycopg://pytest_no_db:pytest_no_db@127.0.0.1:1/pytest_no_db_forbidden",
        )
        monkeypatch.setattr(_db, "get_database_url", _forbid_db_access)
        monkeypatch.setattr(_db, "create_session_factory", _forbid_db_access)
        monkeypatch.setattr(_db, "_build_engine", _forbid_db_access)
        monkeypatch.setattr(_audit_store, "get_database_url", _forbid_db_access)
        monkeypatch.setattr(psycopg, "connect", _forbid_db_access)
        store_mod = sys.modules.get("zw_brain.shared.database_store")
        if store_mod is not None:
            monkeypatch.setattr(store_mod, "create_session_factory", _forbid_db_access)
        _patch_loaded_db_access_aliases(
            monkeypatch,
            get_database_url=original_get_database_url,
            create_session_factory=original_create_session_factory,
        )
        try:
            yield
        finally:
            _reset_engine_cache()
            _reset_audit_globals()
            _restore_env(env_snapshot)
        return

    _configure_durable_test_sink()
    template, server_url, maint = request.getfixturevalue("_pg_template")

    # Deferral: a module-scoped realistic-data fixture (tests/_pg_realistic.py
    # realistic_pg_module) already cloned the realistic template and pinned
    # ZW_BRAIN_DATABASE_URL at it for the whole module. Overwriting that with a
    # fresh EMPTY per-test clone would wipe the real data those tests need, so
    # this function-scoped fixture stays hands-off (hygiene only, no clone).
    if os.environ.get("ZW_BRAIN_TEST_REALISTIC_DB"):
        try:
            yield
        finally:
            _reset_engine_cache()
            _reset_audit_globals()
            _restore_env(env_snapshot)
        return

    saved_default = _db.DEFAULT_PG_URL
    clone = f"zw_test_{uuid.uuid4().hex}"
    clone_url = server_url.set(database=clone).render_as_string(hide_password=False)
    maint.execute(f'CREATE DATABASE "{clone}" TEMPLATE "{template}"')
    # Point BOTH the env knob and the module default at the clone: tests reading
    # ZW_BRAIN_DATABASE_URL get the clone, and tests that POP it (expecting "the
    # default DB") fall through get_database_url() to the clone too — never to a
    # shared, mutation-accumulating default database.
    os.environ.pop("ZW_BRAIN_DB_PATH", None)  # inert under PG, kept tidy
    os.environ[_SERVER_URL_ENV] = clone_url
    _db.DEFAULT_PG_URL = clone_url
    try:
        yield
    finally:
        # This test's engines/audit connection must not bleed into the next one,
        # and must be gone before we DROP the clone.
        _db.DEFAULT_PG_URL = saved_default
        _reset_engine_cache()
        _reset_audit_globals()
        _restore_env(env_snapshot)
        drop_database(maint, clone)
