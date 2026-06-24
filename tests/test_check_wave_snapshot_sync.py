"""Tests for scripts/check_wave_snapshot_sync.py (preflight 段 34 — Wave 真相表 ↔ debt 反向链接)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_wave_snapshot_sync.py"

pytestmark = pytest.mark.no_db


ARCH_DOC_GOOD = """\
# arch

## 〇、文档结构

table here

## 〇.1 当前真相表

| Wave | 状态 | sign-off | 阻塞 |
|---|---|---|---|
| Wave 1 | partial | engineer | AgentRuntime 子项：[preflight-debt §2026-05-24 AgentRuntime](../preflight-debt.md) |
| Wave 2 | partial | — | 真人 sign-off：[preflight-debt §2026-05-24 Wave 2 R14 三引擎](../preflight-debt.md) |

trailing prose.

## 一、我们造什么

body
"""


DEBT_DOC_GOOD = """\
# preflight-debt

intro.

## 2026-05-24 — AgentRuntime runtime 触发式延后（D30 retrofit）

body about AgentRuntime delays.

## 2026-05-24 — Wave 2 R14 三引擎已落地，待 T1 客户演练验证

body about three engines.
"""


DEBT_DOC_BROKEN_DATE = """\
# preflight-debt

## 2026-05-22 — AgentRuntime runtime 触发式延后

date mismatch with arch link.

## 2026-05-24 — Wave 2 R14 三引擎已落地
"""


DEBT_DOC_BROKEN_SUBJECT = """\
# preflight-debt

## 2026-05-24 — 完全不相关的话题

date matches but body talks about something totally different.

## 2026-05-24 — Wave 2 R14 三引擎已落地
"""


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "docs" / "approved").mkdir(parents=True)
    (tmp_path / "docs").mkdir(exist_ok=True)
    return tmp_path


def _write(workspace: Path, arch: str, debt: str) -> tuple[Path, Path]:
    arch_path = workspace / "docs/approved/zw-brain-architecture.md"
    debt_path = workspace / "docs/preflight-debt.md"
    arch_path.write_text(arch)
    debt_path.write_text(debt)
    return arch_path, debt_path


def _run(arch: Path, debt: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--arch", str(arch), "--debt", str(debt)],
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def test_all_links_resolve_passes(workspace: Path) -> None:
    arch, debt = _write(workspace, ARCH_DOC_GOOD, DEBT_DOC_GOOD)
    code, out = _run(arch, debt)
    assert code == 0, f"expected PASS, got {code}\n{out}"
    assert "OK" in out
    assert "2 Wave snapshot link" in out


def test_date_mismatch_fails(workspace: Path) -> None:
    """日期与 ## 标题不一致 → FAIL。"""
    arch, debt = _write(workspace, ARCH_DOC_GOOD, DEBT_DOC_BROKEN_DATE)
    code, out = _run(arch, debt)
    assert code == 1, f"expected FAIL, got {code}\n{out}"
    assert "FAIL" in out
    assert "2026-05-24" in out
    assert "AgentRuntime" in out


def test_subject_mismatch_fails(workspace: Path) -> None:
    """日期匹配但 entry 内无 AgentRuntime 关键词 → FAIL。"""
    arch, debt = _write(workspace, ARCH_DOC_GOOD, DEBT_DOC_BROKEN_SUBJECT)
    code, out = _run(arch, debt)
    assert code == 1, f"expected FAIL, got {code}\n{out}"
    assert "AgentRuntime" in out


def test_warning_only_for_unreferenced_entry(workspace: Path) -> None:
    """debt 有多条 entry 但 arch 只引用一条 → 其余 WARN 非阻塞。"""
    debt_extra = DEBT_DOC_GOOD + """

## 2026-05-23 — 5 个 borderline B1 业务报表 capability

body — 未被 Wave 表引用，应只出 WARN 不阻塞。
"""
    arch, debt = _write(workspace, ARCH_DOC_GOOD, debt_extra)
    code, out = _run(arch, debt)
    assert code == 0, f"expected PASS with WARN, got {code}\n{out}"
    assert "WARN" in out
    assert "borderline" in out
    assert "OK" in out


def test_superseded_entry_not_warned(workspace: Path) -> None:
    """正文含 'superseded' 的 entry 不应触发 WARN。"""
    debt_superseded = DEBT_DOC_GOOD + """

## 2026-05-18 — BFF session store is single-process in-memory — **已 superseded 2026-05-26**

历史条目保留审计链。
"""
    arch, debt = _write(workspace, ARCH_DOC_GOOD, debt_superseded)
    code, out = _run(arch, debt)
    assert code == 0
    # 不应在 WARN 中出现这条 superseded entry
    assert "BFF session store is single-process" not in out


def test_no_snapshot_section_fails(workspace: Path) -> None:
    """arch 中没有 §〇.1 section → FAIL。"""
    arch_text = "# arch\n\n## 一、 something\n\nno snapshot section\n"
    arch, debt = _write(workspace, arch_text, DEBT_DOC_GOOD)
    code, out = _run(arch, debt)
    assert code == 1
    assert "section not found" in out


def test_real_main_head_passes() -> None:
    """段 34 自身在当前 main HEAD 上必须 PASS。"""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, f"check should be green on main HEAD:\n{proc.stdout}\n{proc.stderr}"
