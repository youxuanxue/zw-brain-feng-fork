#!/usr/bin/env bash
# Start zw-brain REST (WebUI) for Cursor Cloud / local preview.
# K12 dashboard BFF retired in 二轮再砍 (详见 D15 二次反转). 仅启动 REST + WebUI.
# Binds 0.0.0.0 by default (see zw_brain.shared.runtime_config) so forwarded preview works.
#
# Backend = PostgreSQL only. The DB is whatever ZW_BRAIN_DATABASE_URL resolves to
# (defaults to local dev PG `postgresql+psycopg://zw_brain:zw_brain@127.0.0.1:5432/zw_brain`);
# bring one up with `docker compose up -d postgres`. Schema is built/migrated by
# ensure_runtime_schema() (alembic forward-migration, D58) on startup.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
else
  PY="$(command -v python3)"
fi

"$PY" <<'PY'
from zw_brain.shared.db import get_database_url
from zw_brain.shared.migrate import ensure_runtime_schema

ensure_runtime_schema()
print("cloud-preview: db ready at", get_database_url())
PY

exec "$PY" -m zw_brain.entry.rest.server
