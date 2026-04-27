from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def test_dashboard_bff_wrapper_imports_from_dashboard_directory() -> None:
    dashboard_dir = REPO_ROOT / "zw-brain-dashboard"
    result = subprocess.run(
        [
            PYTHON,
            "-c",
            "import importlib.util, pathlib; path = pathlib.Path('bff/main.py').resolve(); spec = importlib.util.spec_from_file_location('dashboard_bff_main', path); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); print(hasattr(module, 'DashboardBffHandler')); print(hasattr(module, 'main'))",
        ],
        cwd=dashboard_dir,
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.stdout.strip().splitlines() == ["True", "True"]


def test_dashboard_dockerfile_copies_runtime_dependencies() -> None:
    dockerfile = (REPO_ROOT / "zw-brain-dashboard" / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY zw_brain /app/zw_brain" in dockerfile
    assert "COPY alembic /app/alembic" in dockerfile
    assert "COPY zw-brain-dashboard /app/zw-brain-dashboard" in dockerfile
    assert 'CMD ["python", "zw-brain-dashboard/bff/main.py"]' in dockerfile
