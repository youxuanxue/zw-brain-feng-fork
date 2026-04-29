"""Regression: UI Spec B mechanical gate (scripts/check_ui_spec_b.py)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_check_ui_spec_b_passes() -> None:
    script = REPO_ROOT / "scripts" / "check_ui_spec_b.py"
    proc = subprocess.run([sys.executable, str(script)], cwd=REPO_ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr or proc.stdout
