from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = os.environ.get("PYTHON_FOR_SUBPROCESS") or sys.executable


def test_installed_rest_and_dashboard_http_handler_smoke() -> None:
    with TemporaryDirectory() as tmp:
        dist_dir = Path(tmp) / "dist"
        subprocess.run(
            [PYTHON, "-m", "build", "--wheel", "--outdir", str(dist_dir)],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        wheel = next(dist_dir.glob("zw_brain-*.whl"))

        venv_dir = Path(tmp) / "venv-http"
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        bin_dir = venv_dir / ("Scripts" if os.name == "nt" else "bin")
        python = bin_dir / "python"
        env = os.environ.copy()
        env["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "installed-http.db")
        subprocess.run([str(python), "-m", "pip", "install", str(wheel)], cwd=tmp, env=env, text=True, capture_output=True, check=True)

        rest = subprocess.run(
            [
                str(python),
                "-c",
                "import json, os, threading, urllib.request; from http.server import HTTPServer; from sqlalchemy import create_engine; from zw_brain.domain.models import Base; from zw_brain.shared.migrate import ensure_runtime_schema; import zw_brain.shared.runtime as runtime; from zw_brain.entry.rest.server import RestHandler; ensure_runtime_schema(); engine = create_engine(f\"sqlite:///{os.environ['ZW_BRAIN_DB_PATH']}\", future=True); Base.metadata.create_all(bind=engine); server = HTTPServer(('127.0.0.1', 0), RestHandler); port = server.server_address[1]; thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start(); data = json.loads(urllib.request.urlopen(f'http://127.0.0.1:{port}/health').read().decode()); html = urllib.request.urlopen(f'http://127.0.0.1:{port}/index.html').read().decode(); print(json.dumps({'health': data, 'has_title': '政务数据大脑 · zw-brain' in html}, ensure_ascii=False)); server.shutdown(); server.server_close(); thread.join(timeout=2); runtime._service = None",
            ],
            cwd=tmp,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        rest_data = json.loads(rest.stdout.strip())
        assert rest_data["health"] == {"status": "ok", "service": "zw-brain-rest"}
        assert rest_data["has_title"] is True

        dash = subprocess.run(
            [
                str(python),
                "-c",
                "import json, os, threading, urllib.request; from http.server import HTTPServer; from sqlalchemy import create_engine; from zw_brain.domain.models import Base; from zw_brain.shared.migrate import ensure_runtime_schema; import zw_brain.shared.runtime as runtime; from zw_brain.entry.dashboard_bff import DashboardBffHandler; ensure_runtime_schema(); engine = create_engine(f\"sqlite:///{os.environ['ZW_BRAIN_DB_PATH']}\", future=True); Base.metadata.create_all(bind=engine); server = HTTPServer(('127.0.0.1', 0), DashboardBffHandler); port = server.server_address[1]; thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start(); health = json.loads(urllib.request.urlopen(f'http://127.0.0.1:{port}/health').read().decode()); html = urllib.request.urlopen(f'http://127.0.0.1:{port}/index.html').read().decode(); print(json.dumps({'health': health, 'has_title': '政务大脑 · 大屏' in html}, ensure_ascii=False)); server.shutdown(); server.server_close(); thread.join(timeout=2); runtime._service = None",
            ],
            cwd=tmp,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        dash_data = json.loads(dash.stdout.strip())
        assert dash_data["health"] == {"status": "ok", "writable": False}
        assert dash_data["has_title"] is True
