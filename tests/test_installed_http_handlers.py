from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = os.environ.get("PYTHON_FOR_SUBPROCESS") or sys.executable

# Builds + installs the project wheel into a temp env, then HTTP-smokes the packaged handlers.
# ~14 s locally, ~25 s on CI. Skipped on PR; runs on push-to-main.
pytestmark = pytest.mark.slow_infra


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
                "import json, os, threading, urllib.request; from http.server import HTTPServer; from sqlalchemy import create_engine; from zw_brain.domain.models import Base; from zw_brain.shared.migrate import ensure_runtime_schema; import zw_brain.command.runtime as runtime; from zw_brain.entry.rest.server import RestHandler; urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({}))); ensure_runtime_schema(); engine = create_engine(f\"sqlite:///{os.environ['ZW_BRAIN_DB_PATH']}\", future=True); Base.metadata.create_all(bind=engine); server = HTTPServer(('127.0.0.1', 0), RestHandler); port = server.server_address[1]; thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start(); data = json.loads(urllib.request.urlopen(f'http://127.0.0.1:{port}/health').read().decode()); html = urllib.request.urlopen(f'http://127.0.0.1:{port}/index.html').read().decode(); print(json.dumps({'health': data, 'has_title': '<title>政务数据大脑</title>' in html}, ensure_ascii=False)); server.shutdown(); server.server_close(); thread.join(timeout=2); runtime._service = None",
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
        # K12 dashboard BFF retired (R17 / v4.1): dash HTTP handler test removed.
