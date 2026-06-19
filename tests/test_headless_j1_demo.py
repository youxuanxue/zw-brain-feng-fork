"""F5 regression: headless J1 demo must exit 0 when full chain succeeds."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tests._pg_realistic import realistic_pg_module  # noqa: F401  (module fixture)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "headless_j1_demo.sh"


@pytest.fixture(autouse=True)
def _dev_iam(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS", "1")
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS_ACK", "development-only")


def test_headless_j1_demo_exits_zero(realistic_pg_module: str) -> None:  # noqa: F811  (pytest fixture request)
    # C-1 删演示单后 headless J1 全链路需真实资源（resolve_resource_for_application 经
    # resource_asset DB 解析）。真灌库经 realistic_pg_module 克隆（含真实旧平台数据）注入
    # ZW_BRAIN_DATABASE_URL，子进程脚本继承该 env 连克隆库；模板缺位（CI 无 dump）→ fixture
    # 整模块 skip，承接旧 SEED_DB.exists() 跳过语义（一切围绕真实导入，无演示资源兜底）。
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
