from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.test_legacy_migration_batch import _write_core_dumps

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = os.environ.get("PYTHON_FOR_SUBPROCESS") or sys.executable


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
        assert json.loads(metadata.stdout)["total"] == 1
