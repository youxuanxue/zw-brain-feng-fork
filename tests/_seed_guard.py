"""Shared guard for the real-data (M0 真灌库) tests — PostgreSQL edition.

ORIGIN
------
14 test modules each copy-pasted a ``_seed_ready()`` that gated on a SQLite seed
file (``.data/zw_brain.db``): existence + row COUNT + schema currency. After the
full-PG migration there is no SQLite seed file and no per-file shadow copy: the
realistic legacy dataset lives once in a **persistent PG template database**
(``zw_realistic_tmpl``, built by ``scripts/build_realistic_pg_template``) and each
module that needs it clones the template via the ``realistic_pg_module`` fixture
(``tests/_pg_realistic.py``).

WHAT ``require_real_seed`` MEANS NOW
------------------------------------
The two responsibilities the SQLite guard carried are now owned elsewhere:

* **"real data present, else skip"** → the ``realistic_pg_module`` fixture
  ``pytest.skip``s the whole module when the template DB is absent (CI without
  the legacy dump corpus), exactly reproducing the old skip-when-missing
  semantics.
* **schema currency** → the template is built by running
  ``ensure_runtime_schema()`` (alembic upgrade head) against fresh ORM models, so
  a stale-schema seed is structurally impossible — no per-test PRAGMA diff needed.

So ``require_real_seed`` is a **no-op** retained only to keep the ~24 caller
modules compiling unchanged while their migration to the ``realistic_pg_module``
fixture lands incrementally (a separate slice owns flipping each caller to the
fixture). It never opens a file and never references SQLite. The ``checks`` arg
(row thresholds) is accepted and ignored: D44's rule that runtime-accumulated
tables must never gate a module is still enforced statically by preflight 段 57
(``check_require_real_seed_sanity.py``), independent of this body.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TENANT = "sd-default"

# Build/refresh the realistic PG template that the realistic_pg_module fixture
# clones. Replaces the retired SQLite legacy-import-to-file recipe.
REBUILD_HINT = (
    "重建真灌库（PG realistic 模板，realistic_pg_module 克隆它）："
    ".venv/bin/python -m scripts.build_realistic_pg_template "
    '--dumps-dir "old/10示例数据"  # 灌进 PG 模板库 zw_realistic_tmpl（含审计证据写入）'
)


def require_real_seed(checks: object = None, *, tenant: str = DEFAULT_TENANT) -> None:
    """No-op under PostgreSQL — kept for source compatibility.

    The real-data presence gate (skip when absent) now lives in the
    ``realistic_pg_module`` fixture, and schema currency is guaranteed by the
    migrated template. Modules still calling this should depend on
    ``realistic_pg_module`` for their data; this call no longer touches any file
    or database. ``checks`` / ``tenant`` are accepted and ignored.
    """
    return None
