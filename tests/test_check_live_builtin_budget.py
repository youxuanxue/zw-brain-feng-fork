"""Tests for scripts/check_live_builtin_budget.py (preflight 段 33 — 架构约束 R7 单 prefix budget)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_live_builtin_budget.py"

pytestmark = pytest.mark.no_db


def _make_manifest(
    skill_id: str,
    *,
    status: str = "live",
    binding: str = "builtin",
) -> dict:
    return {
        "skill_id": skill_id,
        "slug": skill_id,
        "title": skill_id,
        "description": "test",
        "version": "1.0.0",
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "execution_binding": binding,
        "product_scope": {"journey": "j1", "status": status},
    }


@pytest.fixture()
def registered_dir(tmp_path: Path) -> Path:
    d = tmp_path / "registered"
    d.mkdir()
    return d


def _run(registered_dir: Path, *, exemptions: Path | None = None, budget: int | None = None) -> tuple[int, str]:
    args = [sys.executable, str(SCRIPT), "--registered-dir", str(registered_dir)]
    if exemptions is not None:
        args.extend(["--exemptions", str(exemptions)])
    if budget is not None:
        args.extend(["--budget", str(budget)])
    proc = subprocess.run(args, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def _seed(d: Path, prefix: str, count: int, *, status: str = "live", binding: str = "builtin") -> None:
    for i in range(count):
        sid = f"{prefix}.cap{i}"
        (d / f"{sid}.json").write_text(json.dumps(_make_manifest(sid, status=status, binding=binding)))


def test_prefix_over_budget_fails(registered_dir: Path) -> None:
    """单 prefix > N → exit 1 + 打印越界 prefix。"""
    _seed(registered_dir, "alpha", 26)
    code, out = _run(registered_dir)
    assert code == 1, f"expected fail (exit 1), got {code}\n{out}"
    assert "alpha" in out
    assert "count= 26" in out
    assert "FAIL" in out


def test_prefix_exactly_at_budget_passes(registered_dir: Path) -> None:
    """单 prefix == N → exit 0 (边界值放过)。"""
    _seed(registered_dir, "alpha", 25)
    code, out = _run(registered_dir)
    assert code == 0, f"expected pass (exit 0), got {code}\n{out}"
    assert "ok" in out
    assert "alpha=25" in out


def test_exempted_prefix_passes(registered_dir: Path, tmp_path: Path) -> None:
    """豁免清单覆盖 prefix → exit 0 即便越界默认 N。"""
    _seed(registered_dir, "alpha", 30)
    exemptions = tmp_path / "exemptions.json"
    exemptions.write_text(json.dumps({"alpha": 30, "_comment": "architecture-review issue R-099"}))
    code, out = _run(registered_dir, exemptions=exemptions)
    assert code == 0, f"expected pass (exit 0), got {code}\n{out}"
    assert "ok" in out


def test_exempted_prefix_still_over_limit_fails(registered_dir: Path, tmp_path: Path) -> None:
    """豁免上限低于实际计数 → 仍 FAIL，且打出 exempt-limit 标签。"""
    _seed(registered_dir, "alpha", 30)
    exemptions = tmp_path / "exemptions.json"
    exemptions.write_text(json.dumps({"alpha": 27}))
    code, out = _run(registered_dir, exemptions=exemptions)
    assert code == 1, f"expected fail (exit 1), got {code}\n{out}"
    assert "exempt-limit=27" in out


def test_non_live_or_non_builtin_not_counted(registered_dir: Path) -> None:
    """status=deferred 或 binding=external_capability 的 manifest 不进 budget。"""
    # 25 live+builtin alpha (==N, pass) + 100 deferred alpha + 100 external alpha
    _seed(registered_dir, "alpha", 25)
    _seed(registered_dir, "alpha-deferred", 100, status="deferred:wave-3")
    _seed(registered_dir, "alpha-ext", 100, binding="external_capability")
    code, out = _run(registered_dir)
    assert code == 0, f"expected pass (exit 0), got {code}\n{out}"


def test_real_main_head_passes() -> None:
    """段 33 自身在当前 main HEAD 上必须 PASS（catalog=23 ≤ N=25）。"""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, f"check should be green on main HEAD:\n{proc.stdout}\n{proc.stderr}"
