from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

import pytest

from tests.test_legacy_migration_batch import _write_core_dumps

# Builds + installs the project wheel into a temp env, then spins up packaged entry points and
# legacy migration tooling. ~20-30 s per test locally, ~40-50 s on CI. Skipped on PR; runs on
# push-to-main where a wheel regression must still gate.
pytestmark = pytest.mark.slow_infra

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = os.environ.get("PYTHON_FOR_SUBPROCESS") or sys.executable


def _request(method: str, url: str) -> tuple[int, str, str]:
    req = Request(url, method=method, headers={"Accept": "application/json"})
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(req) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read().decode("utf-8")
    except HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), exc.read().decode("utf-8")
    except URLError as exc:
        return 0, "", str(exc)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_installed_wheel_legacy_migration_then_runtime_without_dumps() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        dist_dir = root / "dist"
        subprocess.run(
            [PYTHON, "-m", "build", "--wheel", "--outdir", str(dist_dir)],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        wheel = next(dist_dir.glob("zw_brain-*.whl"))
        venv_dir = root / "venv-migration"
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        bin_dir = venv_dir / ("Scripts" if os.name == "nt" else "bin")
        python = bin_dir / "python"
        env = os.environ.copy()
        env["ZW_BRAIN_TENANT_ID"] = "sd-default"
        subprocess.run([str(python), "-m", "pip", "install", str(wheel)], cwd=tmp, env=env, text=True, capture_output=True, check=True)

        dumps_dir = root / "dumps"
        db_path = root / "customer.db"
        report_path = root / "migration-report.json"
        _write_core_dumps(dumps_dir)
        subprocess.run(
            [
                str(bin_dir / "zw-brain-migrate-legacy"),
                "--dumps-dir",
                str(dumps_dir),
                "--db-path",
                str(db_path),
                "--profile",
                "customer-core-v1",
                "--reset-db",
                "--strict",
                "--acceptance",
                "--report",
                str(report_path),
            ],
            cwd=tmp,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["status"] == "succeeded"
        assert report["migration"] == "legacy-one-shot-acceptance"
        assert report["acceptance"]["idempotency"]["verified"] is True
        for entry in dumps_dir.iterdir():
            entry.unlink()

        runtime_env = env | {"ZW_BRAIN_DB_PATH": str(db_path)}
        runtime_env.pop("ZW_BRAIN_LEGACY_DUMPS_DIR", None)
        cli = subprocess.run(
            [str(bin_dir / "zw-brain-cli"), "catalog.browse", "--payload", '{"lifecycle":"all"}'],
            cwd=tmp,
            env=runtime_env,
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(cli.stdout)
        assert any(item["catalog_code"] == "BASE-POP-001" for item in payload["items"])
        assert "13800001111" not in cli.stdout

        metadata = subprocess.run(
            [str(bin_dir / "zw-brain-cli"), "metadata.catalog_item.query", "--payload", "{}"],
            cwd=tmp,
            env=runtime_env,
            text=True,
            capture_output=True,
            check=True,
        )
        metadata_payload = json.loads(metadata.stdout)
        assert metadata_payload["total"] >= 1
        assert any(item["catalog_code"] == "BASE-POP-001" for item in metadata_payload["items"])

        mcp_tools = subprocess.run(
            [str(bin_dir / "zw-brain-mcp"), "list-tools"],
            cwd=tmp,
            env=runtime_env,
            text=True,
            capture_output=True,
            check=True,
        )
        assert any(item["name"] == "catalog.browse" for item in json.loads(mcp_tools.stdout))
        a2a_card = subprocess.run(
            [str(bin_dir / "zw-brain-a2a"), "agent-card"],
            cwd=tmp,
            env=runtime_env,
            text=True,
            capture_output=True,
            check=True,
        )
        assert any(item["id"] == "catalog.browse" for item in json.loads(a2a_card.stdout)["skills"])

        rest_probe = subprocess.run(
            [
                str(python),
                "-c",
                "from zw_brain.entry.rest.server import WEB_ROOT, OPENAPI_PATH; import json; assert (WEB_ROOT/'index.html').exists(); data=json.loads(OPENAPI_PATH.read_text(encoding='utf-8')); assert '/api/skills/catalog.browse' in data['paths']; print(WEB_ROOT)",
            ],
            cwd=tmp,
            env=runtime_env,
            text=True,
            capture_output=True,
            check=True,
        )
        assert "zw-brain-web" in rest_probe.stdout
        dashboard_probe = subprocess.run(
            [
                str(python),
                "-c",
                "from zw_brain.entry.dashboard_bff import DASHBOARD_ROOT; assert (DASHBOARD_ROOT/'index.html').exists(); assert (DASHBOARD_ROOT/'src'/'dashboard.js').exists(); print(DASHBOARD_ROOT)",
            ],
            cwd=tmp,
            env=runtime_env,
            text=True,
            capture_output=True,
            check=True,
        )
        assert "zw-brain-dashboard" in dashboard_probe.stdout


def test_installed_rest_and_dashboard_bff_serve_packaged_assets() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        dist_dir = root / "dist"
        subprocess.run(
            [PYTHON, "-m", "build", "--wheel", "--outdir", str(dist_dir)],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        wheel = next(dist_dir.glob("zw_brain-*.whl"))
        venv_dir = root / "venv-assets"
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        bin_dir = venv_dir / ("Scripts" if os.name == "nt" else "bin")
        python = bin_dir / "python"
        env = os.environ.copy()
        db_path = root / "customer.db"
        env.update(
            {
                "ZW_BRAIN_DB_PATH": str(db_path),
                "ZW_BRAIN_TENANT_ID": "sd-default",
                "NO_PROXY": "127.0.0.1,localhost",
                "no_proxy": "127.0.0.1,localhost",
            }
        )
        subprocess.run([str(python), "-m", "pip", "install", str(wheel)], cwd=tmp, env=env, text=True, capture_output=True, check=True)
        subprocess.run([str(python), "-c", "from zw_brain.shared.migrate import ensure_runtime_schema; ensure_runtime_schema()"], cwd=tmp, env=env, text=True, capture_output=True, check=True)

        rest_port = _free_port()
        rest = subprocess.Popen(
            [str(bin_dir / "zw-brain-rest")],
            cwd=tmp,
            env=env | {"ZW_BRAIN_REST_HOST": "127.0.0.1", "ZW_BRAIN_REST_PORT": str(rest_port)},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            status = 0
            body = ""
            for _ in range(80):
                time.sleep(0.05)
                status, _, body = _request("GET", f"http://127.0.0.1:{rest_port}/health")
                if status == 200:
                    break
            assert status == 200, body
            status, content_type, html = _request("GET", f"http://127.0.0.1:{rest_port}/index.html")
            assert status == 200
            assert content_type.startswith("text/html")
            assert "<title>政务数据大脑</title>" in html
            status, _, openapi_raw = _request("GET", f"http://127.0.0.1:{rest_port}/openapi.json")
            assert status == 200
            assert "/api/skills/catalog.browse" in json.loads(openapi_raw)["paths"]
        finally:
            rest.terminate()
            try:
                rest.wait(timeout=5)
            except subprocess.TimeoutExpired:
                rest.kill()
                rest.wait(timeout=5)

        dashboard_port = _free_port()
        dashboard = subprocess.Popen(
            [str(bin_dir / "zw-brain-dashboard-bff")],
            cwd=tmp,
            env=env | {"ZW_BRAIN_DASHBOARD_BFF_HOST": "127.0.0.1", "ZW_BRAIN_DASHBOARD_BFF_PORT": str(dashboard_port)},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            status = 0
            body = ""
            for _ in range(80):
                time.sleep(0.05)
                status, _, body = _request("GET", f"http://127.0.0.1:{dashboard_port}/health")
                if status == 200:
                    break
            assert status == 200, body
            status, content_type, html = _request("GET", f"http://127.0.0.1:{dashboard_port}/index.html")
            assert status == 200
            assert content_type.startswith("text/html")
            assert "政务数据大脑 · 指挥大屏" in html
            status, _, forbidden_raw = _request("GET", f"http://127.0.0.1:{dashboard_port}/api/skills/request.create")
            assert status == 404
            assert json.loads(forbidden_raw)["error"] in {"UnknownSkillError", "not_found"}
        finally:
            dashboard.terminate()
            try:
                dashboard.wait(timeout=5)
            except subprocess.TimeoutExpired:
                dashboard.kill()
                dashboard.wait(timeout=5)
