"""Tests for scripts/generate_full_scan_exemptions.py (preflight 段 32b)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "generate_full_scan_exemptions.py"


CODE_WITH_EXEMPTIONS = '''\
"""sample module with full-scan-ok exemptions."""
from sqlalchemy import select


class HotModel:
    tenant_id = None
    catalog_code = None


def list_records(session, *, tenant_id="sd-default"):
    # full-scan-ok: J1 申请记录全量被多个 handler 共享；当前单租户 <1k
    return list(
        session.execute(
            select(HotModel).where(HotModel.tenant_id == tenant_id)
        ).scalars()
    )


def list_items(session, *, tenant_id="sd-default", catalog_code=None):
    # full-scan-ok: catalog_code 可选；None 时 tenant-only 全量 item
    statement = select(HotModel).where(HotModel.tenant_id == tenant_id)
    if catalog_code:
        statement = statement.where(HotModel.catalog_code == catalog_code)
    return list(session.execute(statement).scalars())
'''


@pytest.fixture()
def fake_repo(tmp_path: Path) -> Path:
    scan_root = tmp_path / "zw_brain" / "domain" / "repositories"
    scan_root.mkdir(parents=True)
    return tmp_path


def _run(scan_root: Path, out: Path, *, check: bool = False) -> tuple[int, str]:
    args = [sys.executable, str(SCRIPT), "--scan-root", str(scan_root), "--out", str(out)]
    if check:
        args.append("--check")
    proc = subprocess.run(args, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def test_generate_produces_expected_markdown(fake_repo: Path) -> None:
    """生成模式：扫描 → 写 markdown 含期望条目。"""
    code_file = fake_repo / "zw_brain/domain/repositories/sample.py"
    code_file.write_text(CODE_WITH_EXEMPTIONS)
    out = fake_repo / "out.md"
    code, log = _run(fake_repo / "zw_brain", out)
    assert code == 0, log
    md = out.read_text()
    assert "J1 申请记录全量被多个 handler 共享" in md
    assert "catalog_code 可选" in md
    assert "zw_brain/domain/repositories/sample.py:11" in md or "sample.py:" in md
    assert "**2**" in md  # total count
    assert "Review 周期" in md
    assert "§9.7.5" in md  # cross-reference to arch


def test_check_passes_when_synced(fake_repo: Path) -> None:
    """生成 → --check 同步路径必须 PASS。"""
    code_file = fake_repo / "zw_brain/domain/repositories/sample.py"
    code_file.write_text(CODE_WITH_EXEMPTIONS)
    out = fake_repo / "out.md"
    _run(fake_repo / "zw_brain", out)
    code, log = _run(fake_repo / "zw_brain", out, check=True)
    assert code == 0, log
    assert "OK" in log


def test_check_fails_when_drift(fake_repo: Path) -> None:
    """生成完 markdown，然后修改代码（增加新豁免）但不再生成 → --check FAIL。"""
    code_file = fake_repo / "zw_brain/domain/repositories/sample.py"
    code_file.write_text(CODE_WITH_EXEMPTIONS)
    out = fake_repo / "out.md"
    _run(fake_repo / "zw_brain", out)
    # 加一条新豁免但不重生成
    code_file.write_text(
        CODE_WITH_EXEMPTIONS
        + "\n\ndef list_new(session, *, tenant_id='sd-default'):\n"
        + "    # full-scan-ok: 新增的全表扫场景，未登记到 markdown\n"
        + "    return list(session.execute(select(HotModel).where(HotModel.tenant_id == tenant_id)).scalars())\n"
    )
    code, log = _run(fake_repo / "zw_brain", out, check=True)
    assert code == 1, log
    assert "不同步" in log
    assert "generate_full_scan_exemptions" in log


def test_check_fails_when_missing_out(fake_repo: Path) -> None:
    """--check 但 out 不存在 → FAIL。"""
    code_file = fake_repo / "zw_brain/domain/repositories/sample.py"
    code_file.write_text(CODE_WITH_EXEMPTIONS)
    out = fake_repo / "out.md"
    code, log = _run(fake_repo / "zw_brain", out, check=True)
    assert code == 1, log
    assert "缺失" in log


def test_real_main_head_passes() -> None:
    """段 32b 自身在当前 main HEAD 上必须 PASS（baseline 与代码同步）。"""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, f"check should be green on main HEAD:\n{proc.stdout}\n{proc.stderr}"
