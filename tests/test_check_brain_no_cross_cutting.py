"""Tests for scripts/check_brain_no_cross_cutting.py (preflight 段 48 — Action E shim invariants).

Pins the three groups of invariants the segment enforces:

- Group A (cross-cutting): _mutate / _invoke_traced_read / _emit_audit /
  _enqueue_anchor / _append_audit_feed / _record_capability_call must be shims.
- Group B (state sync): _persist / _sync_reference_tables /
  _sync_database_aggregates / _sync_state_views / _sync_request_todos must be shims.
- Group C (retired): _safe_json / _request_by_id / _delivery_by_id /
  _delivery_by_request_id / _find_api_resource / _package_by_id must NOT exist.

The check parses a brain.py source via ast; the tests construct synthetic
brain.py files in a temp dir + monkey-patch BRAIN_FILE to point at them,
then assert exit code + stdout content. The final test runs the real check
on current HEAD to pin the green state at the time of Action E delivery.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_brain_no_cross_cutting.py"

pytestmark = pytest.mark.no_db


def _run_against(fake_brain: Path) -> tuple[int, str]:
    """Run the check against a synthetic brain.py via env override.

    The script reads ``BRAIN_FILE = REPO_ROOT / "zw_brain" / "command" / "brain.py"``
    at module load time; rather than monkey-patching that constant, we run
    the script as a subprocess with PYTHONPATH unmodified but injection of
    a small wrapper that overrides BRAIN_FILE. Simplest: write a tiny
    bootstrap that sets the constant and execs the script body.
    """
    bootstrap = fake_brain.parent / "_run.py"
    bootstrap.write_text(
        f"import sys\n"
        f"sys.path.insert(0, {str(SCRIPT.parent)!r})\n"
        f"import check_brain_no_cross_cutting as mod\n"
        f"mod.BRAIN_FILE = type(mod.BRAIN_FILE)({str(fake_brain)!r})\n"
        f"sys.exit(mod.main())\n"
    )
    proc = subprocess.run(
        [sys.executable, str(bootstrap)],
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def test_inline_emit_audit_body_fails(tmp_path: Path) -> None:
    """A re-introduced inline _emit_audit body (large) must FAIL."""
    fake = tmp_path / "brain.py"
    body = "\n".join(f"        x{i} = {i}" for i in range(15))
    fake.write_text(
        "class BrainService:\n"
        "    def _emit_audit(self, request_id, actor, skill_id, phase, payload):\n"
        + body + "\n"
    )
    code, out = _run_against(fake)
    assert code == 1, f"expected fail, got {code}\n{out}"
    assert "_emit_audit" in out
    assert "FAIL" in out


def test_shim_emit_audit_passes(tmp_path: Path) -> None:
    """A small shim body for _emit_audit must PASS."""
    fake = tmp_path / "brain.py"
    fake.write_text(
        "class BrainService:\n"
        "    def _emit_audit(self, request_id, actor, skill_id, phase, payload):\n"
        "        from zw_brain.command import pipeline_ops\n"
        "        pipeline_ops.emit_audit(None, None, None, None, request_id, actor, skill_id, phase, payload)\n"
    )
    code, out = _run_against(fake)
    assert code == 0, f"expected pass, got {code}\n{out}"
    assert "OK" in out


def test_retired_safe_json_re_added_fails(tmp_path: Path) -> None:
    """Re-introducing _safe_json must FAIL (Group C retirement)."""
    fake = tmp_path / "brain.py"
    fake.write_text(
        "class BrainService:\n"
        "    def _safe_json(self, value):\n"
        "        return value\n"
    )
    code, out = _run_against(fake)
    assert code == 1
    assert "_safe_json" in out
    assert "retired" in out


def test_retired_request_by_id_re_added_fails(tmp_path: Path) -> None:
    """Re-introducing _request_by_id must FAIL."""
    fake = tmp_path / "brain.py"
    fake.write_text(
        "class BrainService:\n"
        "    def _request_by_id(self, request_id):\n"
        "        return None\n"
    )
    code, out = _run_against(fake)
    assert code == 1
    assert "_request_by_id" in out


def test_inline_sync_state_views_fails(tmp_path: Path) -> None:
    """A re-introduced inline _sync_state_views body must FAIL."""
    fake = tmp_path / "brain.py"
    body = "\n".join(f"        x{i} = {i}" for i in range(10))
    fake.write_text(
        "class BrainService:\n"
        "    def _sync_state_views(self):\n"
        + body + "\n"
    )
    code, out = _run_against(fake)
    assert code == 1
    assert "_sync_state_views" in out


def test_no_brain_service_class_fails(tmp_path: Path) -> None:
    """If BrainService class is missing the check FAILs (cannot reason)."""
    fake = tmp_path / "brain.py"
    fake.write_text("def something(): pass\n")
    code, out = _run_against(fake)
    assert code == 1
    assert "BrainService" in out


def test_real_main_head_passes() -> None:
    """段 48 must be green at the time of Action E delivery (HEAD)."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, (
        f"check should be green on Action E HEAD:\n{proc.stdout}\n{proc.stderr}"
    )


# ── Dead private-shim pass (2026-06-14) ──────────────────────────────────────
import ast  # noqa: E402
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("check_brain_no_cross_cutting", SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
sys.path.insert(0, str(SCRIPT.parent))
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]


def _dead_shims_of(src: str, monkeypatch=None):
    """对合成 src 跑 dead_private_shims。

    AST 逻辑与「外部引用扫真实 repo」解耦：默认 stub ``_externally_referenced`` 恒 False，
    使本单测只验证「`_`-前缀 + 零 self.X 内部调用 + 排除 dunder/named-group/public」这套 AST
    判据，不受测试文件自身字面量泄漏影响（守卫保守扫 tests/ 会把测试里的 shim 名当外部引用）。
    """
    tree = ast.parse(src)
    brain = next(
        n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "BrainService"
    )
    if monkeypatch is not None:
        monkeypatch.setattr(_mod, "_externally_referenced", lambda _name: False)
    return _mod.dead_private_shims(tree, brain)


def test_dead_private_shim_with_no_caller_anywhere_is_flagged(monkeypatch) -> None:
    """零内部 self.X + 零外部引用的 `_`-shim 被识别为死。"""
    src = (
        "class BrainService:\n"
        "    def _orphan_shim(self):\n"
        "        return 1\n"
    )
    assert "_orphan_shim" in _dead_shims_of(src, monkeypatch)


def test_private_method_called_internally_is_not_dead(monkeypatch) -> None:
    """有 self.X 内部调用的 `_`-方法不算死（活方法零误判）。"""
    src = (
        "class BrainService:\n"
        "    def _helper(self):\n"
        "        return 2\n"
        "    def run(self):\n"
        "        return self._helper()\n"
    )
    assert "_helper" not in _dead_shims_of(src, monkeypatch)


def test_public_facade_delegator_never_flagged_as_dead(monkeypatch) -> None:
    """public facade delegator（无 `_` 前缀）即便无 self.X 内部调用也不进死 shim 集合。"""
    src = (
        "class BrainService:\n"
        "    def get_resource(self, *a, **k):\n"
        "        return None\n"
    )
    assert _dead_shims_of(src, monkeypatch) == []


def test_dunder_never_flagged_as_dead(monkeypatch) -> None:
    """dunder（__init__ 等，由构造/协议隐式调用）不进死 shim 集合。"""
    src = (
        "class BrainService:\n"
        "    def __init__(self):\n"
        "        self.x = 1\n"
    )
    assert "__init__" not in _dead_shims_of(src, monkeypatch)


def test_externally_referenced_method_is_not_dead(monkeypatch) -> None:
    """有外部引用（zw_brain/+tests/）的 `_`-方法即便无内部 self.X 也算活——守卫保守不误杀。"""
    src = (
        "class BrainService:\n"
        "    def _ref_elsewhere(self):\n"
        "        return 3\n"
    )
    monkeypatch.setattr(_mod, "_externally_referenced", lambda name: name == "_ref_elsewhere")
    tree = ast.parse(src)
    brain = next(
        n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "BrainService"
    )
    assert "_ref_elsewhere" not in _mod.dead_private_shims(tree, brain)


def test_real_brain_baseline_dead_shims_match_ledger() -> None:
    """真实 brain.py 的死 shim 集合 == KNOWN_DEAD_SHIMS 台账（名实相符，零净新增/零过期）。

    用真实 _externally_referenced（扫真实 repo），不 stub——这是端到端钉死现状。
    """
    src = _mod._CANONICAL_BRAIN_FILE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    brain = next(
        n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "BrainService"
    )
    dead = set(_mod.dead_private_shims(tree, brain))
    assert dead == set(_mod.KNOWN_DEAD_SHIMS), (
        f"死 shim 集合与台账不一致：实测 {sorted(dead)} vs 台账 {sorted(_mod.KNOWN_DEAD_SHIMS)}"
    )
