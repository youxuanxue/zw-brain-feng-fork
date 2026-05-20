from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable

# Builds + installs the project wheel into a temp env, then runs packaged entry-point smokes.
# ~15 s locally, ~25-30 s on CI. Skipped on PR; runs on push-to-main.
pytestmark = pytest.mark.slow_infra


def test_installed_rest_and_dashboard_entry_smoke() -> None:
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

        venv_dir = Path(tmp) / "venv-install"
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        bin_dir = venv_dir / ("Scripts" if os.name == "nt" else "bin")
        python = bin_dir / "python"
        env = os.environ.copy()
        env["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "installed.db")
        subprocess.run([str(python), "-m", "pip", "install", str(wheel)], cwd=tmp, env=env, text=True, capture_output=True, check=True)

        rest = subprocess.run(
            [str(python), "-c", "from zw_brain.entry.rest.server import WEB_ROOT; from pathlib import Path; print(WEB_ROOT.exists()); print((WEB_ROOT / 'index.html').exists())"],
            cwd=tmp,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        assert rest.stdout.strip().splitlines() == ["True", "True"]
        # K12 dashboard BFF 退役 (R17 / v4.1)：不再校验 dashboard 资源打包
