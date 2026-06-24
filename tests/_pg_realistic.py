"""Realistic-data PG template helper for the legacy ``SEED_DB`` shadow tests.

Before the full-PG migration these tests did::

    SEED_DB = REPO_ROOT / ".data" / "zw_brain.db"          # sqlite, M0 legacy import
    shutil.copy(SEED_DB, SHADOW_DB)
    os.environ["ZW_BRAIN_DB_PATH"] = str(SHADOW_DB)         # point reads at the copy
    ...
    sqlite3.connect(f"file:{SHADOW_DB}?mode=ro", uri=True)  # direct sqlite reads

PostgreSQL has no per-file copy, so the realistic dataset lives once in a
**persistent template database** (default ``zw_realistic_tmpl``) built by
``scripts/build_realistic_pg_template`` (legacy-import of ``old/10示例数据`` into
PG). Each test module clones it cheaply with ``CREATE DATABASE … TEMPLATE`` —
the PG equivalent of the old ``shutil.copy`` — and points
``ZW_BRAIN_DATABASE_URL`` at the clone for the module's lifetime.

Migration recipe for a ``SEED_DB`` test:
  1. Delete the ``SEED_DB`` / ``SHADOW_DB`` / ``shutil.copy`` / ``ZW_BRAIN_DB_PATH``
     block and the ``require_real_seed`` sqlite-file guard.
  2. Add ``pytestmark = pytest.mark.usefixtures("realistic_pg_module")`` (or
     depend on the ``realistic_pg_module`` fixture) — it provides a freshly
     cloned realistic DB via ``ZW_BRAIN_DATABASE_URL`` and skips the module when
     no template is present (CI without dumps), preserving the old
     ``require_real_seed`` skip semantics.
  3. Replace any ``sqlite3.connect(SHADOW_DB)`` read with the app read path
     (repositories / ``system.snapshot``) or a psycopg query against
     ``zw_brain.shared.db.get_database_url()`` — never reopen a file.

Skip (not fail) when the template is absent so CI — which has no 445 MB dump —
behaves exactly like the old ``require_real_seed`` skip.
"""
from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from sqlalchemy.engine import make_url

from tests._pg_admin import drop_database, maintenance_connect
from zw_brain.shared import db as _db

# Persistent template DB built by scripts/build_realistic_pg_template (legacy
# import of old/10示例数据 into PG). Override the name via env for CI/ops.
REALISTIC_TEMPLATE_DB = os.environ.get("ZW_BRAIN_TEST_REALISTIC_TEMPLATE", "zw_realistic_tmpl")


def _server_url():
    """Server URL the test PG lives on (same resolution as conftest)."""
    return make_url(os.environ.get("ZW_BRAIN_DATABASE_URL") or _db.DEFAULT_PG_URL)


def _template_exists(maint: psycopg.Connection, name: str) -> bool:
    row = maint.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone()
    return row is not None


@pytest.fixture(scope="module")
def realistic_pg_module() -> Iterator[str]:
    """Module-scoped clone of the realistic template; skips when absent.

    Yields the clone database name. Sets ``ZW_BRAIN_DATABASE_URL`` to the clone
    for the module and restores it on teardown. This is the PG replacement for
    the old per-module ``shutil.copy(SEED_DB, SHADOW_DB)`` shadow database.
    """
    server_url = _server_url()
    maint = maintenance_connect(server_url)
    try:
        if not _template_exists(maint, REALISTIC_TEMPLATE_DB):
            pytest.skip(
                f"realistic PG template {REALISTIC_TEMPLATE_DB!r} not present "
                "(build it with scripts/build_realistic_pg_template; CI without "
                "the legacy dump corpus skips these real-data tests)"
            )
        clone = f"zw_real_{uuid.uuid4().hex}"
        drop_database(maint, clone)
        maint.execute(f'CREATE DATABASE "{clone}" TEMPLATE "{REALISTIC_TEMPLATE_DB}"')
        saved_url = os.environ.get("ZW_BRAIN_DATABASE_URL")
        saved_default = _db.DEFAULT_PG_URL
        clone_url = server_url.set(database=clone).render_as_string(hide_password=False)
        os.environ.pop("ZW_BRAIN_DB_PATH", None)
        os.environ["ZW_BRAIN_DATABASE_URL"] = clone_url
        # Marker tells conftest's function-scoped _isolate_db_env to stay
        # hands-off (no empty per-test clone) so this realistic data survives.
        os.environ["ZW_BRAIN_TEST_REALISTIC_DB"] = clone
        _db.DEFAULT_PG_URL = clone_url
        _db.reset_engine_cache()
        try:
            yield clone
        finally:
            _db.reset_engine_cache()
            _db.DEFAULT_PG_URL = saved_default
            os.environ.pop("ZW_BRAIN_TEST_REALISTIC_DB", None)
            if saved_url is None:
                os.environ.pop("ZW_BRAIN_DATABASE_URL", None)
            else:
                os.environ["ZW_BRAIN_DATABASE_URL"] = saved_url
            drop_database(maint, clone)
    finally:
        maint.close()
