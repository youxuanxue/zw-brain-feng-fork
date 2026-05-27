"""段 37 自身的 baseline + 回潮防御 — Phase 1.1。

`scripts/check_brain_no_record_to_dict.py` 守 BrainService 不再持有 record_to_dict
方法。本测试锁两件事：
  1. 当前 HEAD 上 check 自身 PASS（baseline 与代码同步）
  2. 在临时副本里加回一个 record_to_dict 方法，check 必 FAIL（回潮触发）
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_brain_no_record_to_dict.py"


def _run(check_repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        cwd=check_repo,
    )


def test_main_head_passes() -> None:
    """段 37 自身在当前 HEAD 必须 PASS（baseline 与代码同步）。"""
    proc = _run(REPO_ROOT)
    assert proc.returncode == 0, f"段 37 应在当前 HEAD PASS:\n{proc.stdout}\n{proc.stderr}"


def test_regression_introducing_record_to_dict_fails(tmp_path: Path) -> None:
    """在临时副本里给 BrainService 加回一个 record_to_dict 方法，check 必 FAIL。"""
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    (fake_repo / "zw_brain" / "command").mkdir(parents=True)
    (fake_repo / "scripts").mkdir()
    shutil.copy(SCRIPT, fake_repo / "scripts" / "check_brain_no_record_to_dict.py")
    (fake_repo / "zw_brain" / "command" / "brain.py").write_text(
        "from typing import Any\n"
        "class BrainService:\n"
        "    def _fake_record_to_dict(self, item: Any) -> dict[str, Any]:\n"
        "        return {'id': item.id}\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(fake_repo / "scripts" / "check_brain_no_record_to_dict.py")],
        capture_output=True,
        text=True,
        cwd=fake_repo,
    )
    assert proc.returncode == 1, f"回潮应被拦下，实际通过了:\n{proc.stdout}\n{proc.stderr}"
    assert "_fake_record_to_dict" in proc.stdout


def test_topic_package_detail_to_dict_is_exempt(tmp_path: Path) -> None:
    """`_topic_package_detail_to_dict` 是 aggregate view，白名单豁免。"""
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    (fake_repo / "zw_brain" / "command").mkdir(parents=True)
    (fake_repo / "scripts").mkdir()
    shutil.copy(SCRIPT, fake_repo / "scripts" / "check_brain_no_record_to_dict.py")
    (fake_repo / "zw_brain" / "command" / "brain.py").write_text(
        "from typing import Any\n"
        "class BrainService:\n"
        "    def _topic_package_detail_to_dict(self, item: Any) -> dict[str, Any]:\n"
        "        return {'package_code': item.package_code}\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(fake_repo / "scripts" / "check_brain_no_record_to_dict.py")],
        capture_output=True,
        text=True,
        cwd=fake_repo,
    )
    assert proc.returncode == 0, f"豁免清单内的方法不应被拦:\n{proc.stdout}\n{proc.stderr}"
