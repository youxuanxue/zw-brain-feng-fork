from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def test_wheel_build_and_install_smoke() -> None:
    with TemporaryDirectory() as tmp:
        dist_dir = Path(tmp) / "dist"
        wheel_env = os.environ.copy()
        subprocess.run(
            [PYTHON, "-m", "pip", "install", "build"],
            cwd=REPO_ROOT,
            env=wheel_env,
            text=True,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            [PYTHON, "-m", "build", "--wheel", "--outdir", str(dist_dir)],
            cwd=REPO_ROOT,
            env=wheel_env,
            text=True,
            capture_output=True,
            check=True,
        )
        wheels = sorted(dist_dir.glob("zw_brain-*.whl"))
        assert wheels, "wheel was not built"

        venv_dir = Path(tmp) / "venv-install"
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        bin_dir = venv_dir / ("Scripts" if os.name == "nt" else "bin")
        python = bin_dir / "python"
        env = os.environ.copy()
        env["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "installed.db")
        subprocess.run([str(python), "-m", "pip", "install", str(wheels[0])], cwd=tmp, env=env, text=True, capture_output=True, check=True)

        subprocess.run(
            [str(python), "-c", "from zw_brain.shared.migrate import ensure_runtime_schema; ensure_runtime_schema(); print('ok')"],
            cwd=tmp,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )

        cli = subprocess.run(
            [str(python), "-m", "zw_brain.entry.cli.main", "data.search", "--payload", '{\"query\":\"法人\",\"role\":\"r1\"}'],
            cwd=tmp,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        assert "results" in cli.stdout

        site_root = next((p for p in python.parent.parent.glob("lib/python*/site-packages")), None)
        assert site_root is not None
        assert (site_root / "zw_brain" / "entry" / "rest" / "openapi.json").exists()
        assert (site_root / "zw_brain" / "entry" / "a2a" / "agent_card.json").exists()
        assert (site_root / "zw_brain" / "_assets" / "zw-brain-dashboard" / "src" / "dashboard.js").exists()
        assert (site_root / "zw_brain" / "_assets" / "zw-brain-web" / "index.html").exists()
        assert (site_root / "zw_brain" / "_assets" / "alembic" / "env.py").exists()
        assert (site_root / "zw_brain" / "_assets" / "alembic.ini").exists()

        migrate = subprocess.run(
            [str(bin_dir / "zw-brain-migrate-legacy"), "--help"],
            cwd=tmp,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        assert "One-shot legacy dump migration" in migrate.stdout
