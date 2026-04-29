#!/usr/bin/env bash
# Start zw-brain REST (WebUI) + dashboard BFF for Cursor Cloud / local preview.
# Binds 0.0.0.0 by default (see zw_brain.shared.runtime_config) so forwarded preview works.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"
export ZW_BRAIN_DB_PATH="${ZW_BRAIN_DB_PATH:-/tmp/zw-brain-preview.db}"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
else
  PY="$(command -v python3)"
fi

"$PY" <<'PY'
import os
from sqlalchemy import create_engine
from zw_brain.domain.models import Base
from zw_brain.shared.migrate import ensure_runtime_schema

ensure_runtime_schema()
engine = create_engine(f"sqlite:///{os.environ['ZW_BRAIN_DB_PATH']}", future=True)
Base.metadata.create_all(bind=engine)
print("cloud-preview: db ready at", os.environ["ZW_BRAIN_DB_PATH"])
PY

# Dashboard BFF uses get_dashboard_bff_port() → rest port + 1 when unset
"$PY" "$ROOT/zw-brain-dashboard/bff/main.py" &
exec "$PY" -m zw_brain.entry.rest.server
