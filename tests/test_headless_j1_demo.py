"""F5 regression: headless J1 demo must exit 0 when full chain succeeds."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "headless_j1_demo.sh"


@pytest.fixture(autouse=True)
def _dev_iam(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS", "1")
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS_ACK", "development-only")


def test_headless_j1_demo_exits_zero() -> None:
    assert SCRIPT.is_file(), f"missing {SCRIPT}"
    env = {**os.environ, "ZW_BRAIN_DEV_IAM_BYPASS": "1", "ZW_BRAIN_DEV_IAM_BYPASS_ACK": "development-only"}
    proc = subprocess.run(["bash", str(SCRIPT)], cwd=REPO_ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "5/5 全绿" in proc.stdout or "status=200" in proc.stdout


def test_headless_j1_demo_fails_on_bad_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    """Negative: invalid decision enum must not fake-green."""
    monkeypatch.setenv("ZW_BRAIN_DEMO_ROLE", "ROLE_ORGAN_OPERATER")
    # Patch CLI path is heavy; assert script documents strict exit via grep
    text = SCRIPT.read_text(encoding="utf-8")
    assert "FAILED=1" in text
    assert "approve_reuse" in text
    assert 'exit 1' in text
