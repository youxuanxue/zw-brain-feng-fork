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

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_brain_no_cross_cutting.py"


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
