from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from zw_brain.domain.models import Base
from zw_brain.entry.rest.server import RestHandler
from zw_brain.shared.migrate import ensure_runtime_schema
import zw_brain.shared.runtime as runtime
from sqlalchemy import create_engine


def request_json(method: str, url: str, body: dict | None = None) -> tuple[int, dict | str]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(req) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read().decode("utf-8")
            if content_type.startswith("application/json"):
                return resp.status, json.loads(raw)
            return resp.status, raw
    except HTTPError as exc:
        payload = json.loads(exc.read().decode("utf-8"))
        return exc.code, payload


def test_rest_runtime_exposes_openapi_and_capability_endpoints() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)
        runtime._service = None
        ensure_runtime_schema()
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        Base.metadata.create_all(bind=engine)

        from http.server import HTTPServer
        from threading import Thread

        server = HTTPServer(("127.0.0.1", 0), RestHandler)
        port = server.server_address[1]
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, health = request_json("GET", f"http://127.0.0.1:{port}/health")
            assert status == 200
            assert health == {"status": "ok", "service": "zw-brain-rest"}

            with urlopen(f"http://127.0.0.1:{port}/openapi.json") as resp:
                assert resp.status == 200
                openapi = json.loads(resp.read().decode("utf-8"))
            assert "/api/skills/request.create" in openapi["paths"]
            assert "/api/skills/data.search" in openapi["paths"]

            status, result = request_json(
                "GET",
                f"http://127.0.0.1:{port}/api/skills/data.search?query=%E6%B3%95%E4%BA%BA&page=1&role=r1",
            )
            assert status == 200
            assert result["results"]

            status, confirmation = request_json(
                "POST",
                f"http://127.0.0.1:{port}/api/skills/request.create",
                {"resource_id": "res-market-activity", "role": "r1", "confirmed": False},
            )
            assert status == 409
            assert confirmation["error"] == "confirmation_required"
            assert confirmation["skill_id"] == "request.create"

            status, created = request_json(
                "POST",
                f"http://127.0.0.1:{port}/api/skills/request.create",
                {
                    "resource_id": "res-market-activity",
                    "query": "我要发起市场主体活跃度复用申请",
                    "role": "r1",
                    "confirmed": True,
                },
            )
            assert status == 200
            request_id = created["result"]["request_id"]

            status, request_view = request_json(
                "GET",
                f"http://127.0.0.1:{port}/api/skills/request.view?request_id={request_id}&role=r1",
            )
            assert status == 200
            assert request_view["id"] == request_id
            assert request_view["status"] == "pending"

            status, duplicate = request_json(
                "POST",
                f"http://127.0.0.1:{port}/api/skills/request.create",
                {"resource_id": "res-market-activity", "role": "r1", "confirmed": True},
            )
            assert status == 409
            assert duplicate["error"] == "invalid_state"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            runtime._service = None


def test_rest_runtime_serves_main_webui_shell_and_enforces_access_denied() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)
        runtime._service = None
        ensure_runtime_schema()
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        Base.metadata.create_all(bind=engine)

        from http.server import HTTPServer
        from threading import Thread

        server = HTTPServer(("127.0.0.1", 0), RestHandler)
        port = server.server_address[1]
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, html = request_json("GET", f"http://127.0.0.1:{port}/index.html")
            assert status == 200
            assert "政务数据大脑 · zw-brain" in html
            assert "P1–P8 + K12" in html

            status, denied = request_json(
                "POST",
                f"http://127.0.0.1:{port}/api/skills/approval.review_decide",
                {"request_id": "REQ-2026-04-25-0011", "decision": "approve", "role": "r1", "confirmed": True},
            )
            assert status == 403
            assert denied["error"] == "access_denied"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            runtime._service = None
