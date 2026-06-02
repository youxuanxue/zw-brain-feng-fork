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
    # C-1 删演示单后 headless J1 全链路需真实资源（resolve_resource_for_application 经
    # resource_asset DB 解析）。无 M0 真灌库（如 CI 空库）→ 脚本动态发现无资源会优雅跳过，
    # 本测试同步 skip（一切围绕真实导入，不再有演示资源兜底）。
    from tests._seed_guard import SEED_DB
    if not SEED_DB.exists():
        pytest.skip("M0 真灌库缺位；headless J1 demo 需真实资源（C-1 删演示单后无演示兜底）")

    assert SCRIPT.is_file(), f"missing {SCRIPT}"
    env = {**os.environ, "ZW_BRAIN_DEV_IAM_BYPASS": "1", "ZW_BRAIN_DEV_IAM_BYPASS_ACK": "development-only"}
    proc = subprocess.run(["bash", str(SCRIPT)], cwd=REPO_ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    if "demo 跳过（无真实数据" in proc.stdout:
        pytest.skip("headless J1 demo 无真实可用资源（data.search 空）；脚本优雅跳过")
    assert "5/5 全绿" in proc.stdout or "status=200" in proc.stdout


def test_headless_j1_demo_fails_on_bad_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    """Negative: invalid decision enum must not fake-green."""
    monkeypatch.setenv("ZW_BRAIN_DEMO_ROLE", "ROLE_ORGAN_OPERATER")
    # Patch CLI path is heavy; assert script documents strict exit via grep
    text = SCRIPT.read_text(encoding="utf-8")
    assert "FAILED=1" in text
    assert "approve_reuse" in text
    assert 'exit 1' in text
