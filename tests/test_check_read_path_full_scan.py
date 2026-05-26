"""Tests for scripts/check_read_path_full_scan.py (preflight 段 32 — PR #113 教训机械化)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_read_path_full_scan.py"


# 三类样例文件 ── 模拟 zw_brain/domain/repositories/ 下的真实读路径形态
VIOLATION_PR113 = '''\
"""Simulates the pre-#113 catalog.entry.query bug pattern."""
from sqlalchemy import select


class CatalogEntryRecord:
    tenant_id = None
    catalog_code = None


def list_entries(session, *, tenant_id="sd-default") -> list:
    return list(
        session.execute(
            select(CatalogEntryRecord)
            .where(CatalogEntryRecord.tenant_id == tenant_id)
            .order_by(CatalogEntryRecord.catalog_code)
        ).scalars()
    )
'''


CLEAN_WITH_LIMIT = '''\
"""Clean: limit() present."""
from sqlalchemy import select


class CatalogEntryRecord:
    tenant_id = None
    catalog_code = None


def list_entries(session, *, tenant_id="sd-default", limit=50) -> list:
    return list(
        session.execute(
            select(CatalogEntryRecord)
            .where(CatalogEntryRecord.tenant_id == tenant_id)
            .order_by(CatalogEntryRecord.catalog_code)
            .limit(limit)
        ).scalars()
    )
'''


CLEAN_WITH_EXTRA_FILTER = '''\
"""Clean: filter dimension beyond tenant_id."""
from sqlalchemy import select


class CatalogEntryRecord:
    tenant_id = None
    catalog_code = None
    lifecycle_status = None


def list_entries(session, *, tenant_id="sd-default", lifecycle_status="published") -> list:
    return list(
        session.execute(
            select(CatalogEntryRecord)
            .where(
                CatalogEntryRecord.tenant_id == tenant_id,
                CatalogEntryRecord.lifecycle_status == lifecycle_status,
            )
            .order_by(CatalogEntryRecord.catalog_code)
        ).scalars()
    )
'''


VAR_ASSIGNED_VIOLATION = '''\
"""Simulates PR #113 pattern but with statement variable assignment.

`statement = select(HotModel).where(tenant_only)` then `session.execute(statement)`
仍是 #113 同类全扫；check 必须穿透变量赋值识别。
"""
from sqlalchemy import select


class CatalogEntryRecord:
    tenant_id = None
    catalog_code = None


def list_entries(session, *, tenant_id="sd-default") -> list:
    statement = select(CatalogEntryRecord).where(CatalogEntryRecord.tenant_id == tenant_id)
    return list(session.execute(statement.order_by(CatalogEntryRecord.catalog_code)).scalars())
'''


VAR_ASSIGNED_CLEAN = '''\
"""变量赋值场景下，续链加 limit 后必须通过。"""
from sqlalchemy import select


class CatalogEntryRecord:
    tenant_id = None
    catalog_code = None


def list_entries(session, *, tenant_id="sd-default", limit=50) -> list:
    statement = select(CatalogEntryRecord).where(CatalogEntryRecord.tenant_id == tenant_id)
    statement = statement.limit(limit)
    return list(session.execute(statement).scalars())
'''


EXEMPTED = '''\
"""Exempted with full-scan-ok reason."""
from sqlalchemy import select


class CatalogEntryRecord:
    tenant_id = None
    catalog_code = None


def list_all_entries(session, *, tenant_id="sd-default") -> list:
    # full-scan-ok: legacy verification 一次性 count 用途；trigger: 多租户接入
    return list(
        session.execute(
            select(CatalogEntryRecord)
            .where(CatalogEntryRecord.tenant_id == tenant_id)
            .order_by(CatalogEntryRecord.catalog_code)
        ).scalars()
    )
'''


OPTIONAL_FILTER_VIOLATION = '''\
"""Optional if-filter must not mask tenant-only default path."""
from sqlalchemy import select


class CatalogEntryRecord:
    tenant_id = None
    lifecycle_status = None


def list_entries(session, *, tenant_id="sd-default", lifecycle_status=None) -> list:
    statement = (
        select(CatalogEntryRecord)
        .where(CatalogEntryRecord.tenant_id == tenant_id)
        .order_by(CatalogEntryRecord.catalog_code)
    )
    if lifecycle_status:
        statement = statement.where(CatalogEntryRecord.lifecycle_status == lifecycle_status)
    return list(session.execute(statement).scalars())
'''


RETURN_BUILDER_VIOLATION = '''\
"""Query builder return tenant-only statement must be caught."""
from sqlalchemy import select


class CatalogEntryRecord:
    tenant_id = None


def build_entry_statement(tenant_id="sd-default"):
    statement = (
        select(CatalogEntryRecord)
        .where(CatalogEntryRecord.tenant_id == tenant_id)
        .order_by(CatalogEntryRecord.catalog_code)
    )
    return statement
'''


@pytest.fixture()
def fake_repo(tmp_path: Path) -> Path:
    """构造一个最小目录树，模拟 zw_brain/domain/repositories/ + scripts/ + 脚本。

    返回 fake_repo 根路径；脚本以 --root <fake_repo> 调用。
    """
    repos = tmp_path / "zw_brain" / "domain" / "repositories"
    repos.mkdir(parents=True)
    # 复制脚本到 fake_repo/scripts/，让脚本以 fake_repo 为 root 扫描
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    shutil.copy(SCRIPT, scripts_dir / SCRIPT.name)
    return tmp_path


def _run(repo: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(repo)],
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def test_violation_pr113_pattern_fails(fake_repo: Path) -> None:
    """PR #113 类的 tenant-only 全扫必须被捕获 → exit 1。"""
    (fake_repo / "zw_brain/domain/repositories/catalog.py").write_text(VIOLATION_PR113)
    code, out = _run(fake_repo)
    assert code == 1, f"expected fail (exit 1), got {code}\n{out}"
    assert "CatalogEntryRecord" in out
    assert "list_entries" in out or "session.execute" in out
    assert "FAIL" in out


def test_clean_with_limit_passes(fake_repo: Path) -> None:
    """带 .limit() 的查询必须通过 → exit 0。"""
    (fake_repo / "zw_brain/domain/repositories/catalog.py").write_text(CLEAN_WITH_LIMIT)
    code, out = _run(fake_repo)
    assert code == 0, f"expected pass (exit 0), got {code}\n{out}"
    assert "OK" in out


def test_clean_with_extra_filter_passes(fake_repo: Path) -> None:
    """带 lifecycle_status 业务维度的查询必须通过 → exit 0。"""
    (fake_repo / "zw_brain/domain/repositories/catalog.py").write_text(CLEAN_WITH_EXTRA_FILTER)
    code, out = _run(fake_repo)
    assert code == 0, f"expected pass (exit 0), got {code}\n{out}"
    assert "OK" in out


def test_var_assigned_violation_caught(fake_repo: Path) -> None:
    """`statement = select(HotModel).where(tenant_only); execute(statement.order_by(...))` —
    PR #113 同模式但用 statement 变量；check 必须穿透变量赋值识别。"""
    (fake_repo / "zw_brain/domain/repositories/catalog.py").write_text(VAR_ASSIGNED_VIOLATION)
    code, out = _run(fake_repo)
    assert code == 1, f"expected fail (exit 1), got {code}\n{out}"
    assert "CatalogEntryRecord" in out
    assert "FAIL" in out


def test_var_assigned_clean_passes(fake_repo: Path) -> None:
    """变量赋值 + 续链 limit 必须通过。"""
    (fake_repo / "zw_brain/domain/repositories/catalog.py").write_text(VAR_ASSIGNED_CLEAN)
    code, out = _run(fake_repo)
    assert code == 0, f"expected pass (exit 0), got {code}\n{out}"
    assert "OK" in out


def test_exempted_passes(fake_repo: Path) -> None:
    """带 # full-scan-ok: <理由> 豁免的查询必须通过 → exit 0。"""
    (fake_repo / "zw_brain/domain/repositories/catalog.py").write_text(EXEMPTED)
    code, out = _run(fake_repo)
    assert code == 0, f"expected pass (exit 0), got {code}\n{out}"
    assert "OK" in out


def test_optional_filter_violation_caught(fake_repo: Path) -> None:
    """``if lifecycle_status: statement.where(...)`` 不能把默认 None 路径假阴性放过。"""
    (fake_repo / "zw_brain/domain/repositories/catalog.py").write_text(OPTIONAL_FILTER_VIOLATION)
    code, out = _run(fake_repo)
    assert code == 1, f"expected fail (exit 1), got {code}\n{out}"
    assert "CatalogEntryRecord" in out
    assert "FAIL" in out


def test_return_builder_violation_caught(fake_repo: Path) -> None:
    """``return statement`` query builder 仅 tenant 时必须被捕获。"""
    (fake_repo / "zw_brain/domain/repositories/catalog.py").write_text(RETURN_BUILDER_VIOLATION)
    code, out = _run(fake_repo)
    assert code == 1, f"expected fail (exit 1), got {code}\n{out}"
    assert "CatalogEntryRecord" in out
    assert "FAIL" in out


def test_real_main_head_passes() -> None:
    """段 32 自身在当前 main HEAD 上必须 PASS（hot tables 已加豁免标签）。"""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, f"check should be green on main HEAD:\n{proc.stdout}\n{proc.stderr}"
