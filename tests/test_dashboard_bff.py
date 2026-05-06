from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sqlalchemy import create_engine

import zw_brain.command.runtime as runtime
from zw_brain.domain.models import Base
from zw_brain.shared.migrate import ensure_runtime_schema


def request(method: str, url: str) -> tuple[int, str, str]:
    req = Request(url, method=method, headers={"Accept": "application/json"})
    try:
        with urlopen(req) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read().decode("utf-8")
    except HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), exc.read().decode("utf-8")


def test_dashboard_bff_is_readonly_and_serves_dashboard_skill() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)
        runtime._service = None
        ensure_runtime_schema()
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        Base.metadata.create_all(bind=engine)

        from http.server import HTTPServer
        from importlib.util import module_from_spec, spec_from_file_location
        from threading import Thread

        from zw_brain_dashboard_bff import main as _  # noqa: F401

        module_path = Path(__file__).resolve().parents[1] / "zw-brain-dashboard" / "bff" / "main.py"
        spec = spec_from_file_location("zw_brain_dashboard_bff_impl", module_path)
        module = module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        handler = module.DashboardBffHandler

        server = HTTPServer(("127.0.0.1", 0), handler)
        port = server.server_address[1]
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, content_type, health_raw = request("GET", f"http://127.0.0.1:{port}/health")
            assert status == 200
            assert content_type.startswith("application/json")
            assert json.loads(health_raw) == {"status": "ok", "writable": False}

            status, content_type, dashboard_raw = request("GET", f"http://127.0.0.1:{port}/api/skills/dashboard.render_command_center")
            assert status == 200
            assert content_type.startswith("application/json")
            dashboard = json.loads(dashboard_raw)
            assert dashboard["mode"] in {"live-readonly", "snapshot"}
            assert dashboard["summary"]

            status, content_type, html = request("GET", f"http://127.0.0.1:{port}/index.html")
            assert status == 200
            assert content_type.startswith("text/html")
            assert "政务数据大脑 · 指挥大屏" in html

            status, content_type, js = request("GET", f"http://127.0.0.1:{port}/src/dashboard.js")
            assert status == 200
            assert "loadDashboard" in js

            status, content_type, forbidden_raw = request("GET", f"http://127.0.0.1:{port}/api/skills/request.create")
            assert status == 404
            assert content_type.startswith("application/json")
            forbidden = json.loads(forbidden_raw)
            assert forbidden["error"] in {"UnknownSkillError", "not_found"}
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            runtime._service = None
