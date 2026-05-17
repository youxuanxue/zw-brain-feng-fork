from __future__ import annotations

import json
import os
import subprocess
import sys
from http.server import HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread

import pytest

import zw_brain.command.runtime as runtime
from tests.test_legacy_migration_batch import _write_core_dumps
from tests.test_rest_runtime import request_json
from zw_brain.adapters.legacy.migration_batch import MigrationOptions, run_acceptance_migration
from zw_brain.command.runtime import get_service, reset_service

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
RUNTIME_DIRS = ("zw_brain/entry", "zw_brain/command", "zw_brain/domain", "zw_brain/shared")
ALLOWED_LEGACY_RUNTIME_FILES = {
    "zw_brain/entry/legacy_migration/main.py",
    "zw_brain/domain/repositories/legacy_mapping.py",
}


def _runtime_env(db_path: Path, legacy_source: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["ZW_BRAIN_DB_PATH"] = str(db_path)
    env["ZW_BRAIN_LEGACY_DUMPS_DIR"] = str(legacy_source)
    return env


def _prepare_imported_db(root: Path) -> tuple[Path, Path]:
    dumps_dir = root / "dumps"
    db_path = root / "customer.db"
    _write_core_dumps(dumps_dir)
    report = run_acceptance_migration(MigrationOptions(dumps_dir=dumps_dir, db_path=db_path, strict=True))
    assert report["status"] == "succeeded"
    for entry in dumps_dir.iterdir():
        entry.unlink()
    dumps_dir.rmdir()
    return db_path, root / "legacy-source-is-offline"


def test_runtime_service_cli_and_rest_work_after_legacy_source_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path, offline_legacy_source = _prepare_imported_db(root)
        monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
        monkeypatch.setenv("ZW_BRAIN_LEGACY_DUMPS_DIR", str(offline_legacy_source))
        monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
        monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
        reset_service()

        service = get_service()
        catalog = service.invoke_skill("catalog.browse", {"lifecycle": "all", "role": "r1"})
        assert any(item["catalog_code"] == "BASE-POP-001" for item in catalog["items"])
        entry = service.invoke_skill("catalog.entry.query", {"catalog_code": "BASE-POP-001", "role": "r1"})
        metadata = service.invoke_skill("metadata.catalog_item.query", {"role": "r7"})
        policy = service.invoke_skill("tenant.policy.evaluate", {"capability_id": "catalog.browse", "surface": "api", "role": "r7"})
        assert entry["total"] == 1
        assert metadata["total"] >= 1
        assert any(item["catalog_code"] == "BASE-POP-001" for item in metadata["items"])
        assert policy["source"] in {"brain_registry", "fail_closed", "tenant_capability_policy"}
        assert "13800001111" not in json.dumps([catalog, entry, metadata, policy], ensure_ascii=False)

        published = service.invoke_skill("catalog.entry.publish", {"catalog_code": "BASE-POP-001", "role": "r7", "confirmed": True})
        assert published["ok"] is True
        assert published["result"]["lifecycle_status"] == "active"
        audit = service.invoke_skill("audit.list", {"role": "r7"})
        assert any(item["type"] == "catalog.entry.publish.after" for item in audit["items"])
        assert "13800001111" not in json.dumps(audit, ensure_ascii=False)
        reset_service()

        env = _runtime_env(db_path, offline_legacy_source)
        cli = subprocess.run(
            [PYTHON, "-m", "zw_brain.entry.cli.main", "catalog.browse", "--payload", '{"lifecycle":"all","role":"r1"}'],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        cli_payload = json.loads(cli.stdout)
        assert any(item["catalog_code"] == "BASE-POP-001" for item in cli_payload["items"])
        assert "13800001111" not in cli.stdout

        from zw_brain.entry.rest.server import RestHandler

        runtime._service = None
        server = HTTPServer(("127.0.0.1", 0), RestHandler)
        port = server.server_address[1]
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, body = request_json("GET", f"http://127.0.0.1:{port}/api/skills/catalog.browse?lifecycle=all&role=r1")
            assert status == 200
            assert any(item["catalog_code"] == "BASE-POP-001" for item in body["items"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            runtime._service = None


def test_runtime_layers_do_not_import_legacy_adapter_or_dumps() -> None:
    forbidden_tokens = (
        "zw_brain.adapters.legacy",
        "ZW_BRAIN_LEGACY_DUMPS_DIR",
        "dump_path_for(",
        "list_dumps(",
    )
    violations: list[str] = []
    for root in RUNTIME_DIRS:
        for path in (REPO_ROOT / root).rglob("*.py"):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel in ALLOWED_LEGACY_RUNTIME_FILES:
                continue
            text = path.read_text(encoding="utf-8")
            for token in forbidden_tokens:
                if token in text:
                    violations.append(f"{rel}: {token}")
    assert violations == []


def test_runtime_outputs_do_not_expose_legacy_secret_facts() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path, offline_legacy_source = _prepare_imported_db(root)
        env = _runtime_env(db_path, offline_legacy_source)
        outputs = []
        for skill_id, payload in [
            ("catalog.browse", '{"lifecycle":"all","role":"r1"}'),
            ("catalog.entry.query", '{"catalog_code":"BASE-POP-001","role":"r1"}'),
            ("metadata.catalog_item.query", '{"role":"r7"}'),
            ("audit.list", '{"role":"r7"}'),
        ]:
            result = subprocess.run(
                [PYTHON, "-m", "zw_brain.entry.cli.main", skill_id, "--payload", payload],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=True,
            )
            outputs.append(result.stdout.lower())
        combined = "\n".join(outputs)
        for forbidden in ["password", "client_secret", "access_token", "refresh_token", "session_id", "permission_sql"]:
            assert forbidden not in combined
        assert "13800001111" not in combined
