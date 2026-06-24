"""Tests for debt_status_lib — debt-as-function 现算 (D46 同构).

Covers the four assert kinds (grep_present / grep_absent / script / external)
and the three derived states (open / stale-fixed / invalid), plus the empty-ledger
green path. Each debt doc + its grep target / script module live in a tmp tree so
the test is hermetic (never touches the repo's real .testing/debt/).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_db

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import debt_status_lib as lib  # noqa: E402


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Point debt_status_lib at a tmp REPO_ROOT + .testing/debt/."""
    debt_dir = tmp_path / ".testing" / "debt"
    debt_dir.mkdir(parents=True)
    monkeypatch.setattr(lib, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(lib, "DEBT_DIR", debt_dir)
    return tmp_path


def _write_debt(sandbox: Path, slug: str, body: str) -> Path:
    path = sandbox / ".testing" / "debt" / f"{slug}.debt.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_empty_ledger_is_green(sandbox):
    assert lib.compute_statuses() == []


def test_grep_present_open_when_pattern_present(sandbox):
    (sandbox / "code.py").write_text("x = legacy_full_scan()\n", encoding="utf-8")
    _write_debt(
        sandbox,
        "grep-present-open",
        "slug: grep-present-open\n"
        "title: legacy full scan still in code\n"
        "date: 2026-05-31\n"
        "severity: high\n"
        "assert:\n"
        "  kind: grep_present\n"
        "  file: code.py\n"
        "  pattern: legacy_full_scan\n",
    )
    [st] = lib.compute_statuses()
    assert st.state == lib.OPEN
    assert st.kind == "grep_present"


def test_grep_present_stale_when_pattern_gone(sandbox):
    (sandbox / "code.py").write_text("x = clean_indexed_get()\n", encoding="utf-8")
    _write_debt(
        sandbox,
        "grep-present-stale",
        "slug: grep-present-stale\n"
        "title: legacy full scan (already fixed)\n"
        "date: 2026-05-31\n"
        "severity: medium\n"
        "assert:\n"
        "  kind: grep_present\n"
        "  file: code.py\n"
        "  pattern: legacy_full_scan\n",
    )
    [st] = lib.compute_statuses()
    assert st.state == lib.STALE_FIXED


def test_grep_absent_open_when_fix_not_present(sandbox):
    # open ⇔ pattern absent (the fix marker is not yet there)
    (sandbox / "code.py").write_text("# no fix yet\n", encoding="utf-8")
    _write_debt(
        sandbox,
        "grep-absent-open",
        "slug: grep-absent-open\n"
        "title: fix marker not yet present\n"
        "date: 2026-05-31\n"
        "severity: low\n"
        "assert:\n"
        "  kind: grep_absent\n"
        "  file: code.py\n"
        "  pattern: FIXED_MARKER\n",
    )
    [st] = lib.compute_statuses()
    assert st.state == lib.OPEN


def test_grep_absent_stale_when_fix_present(sandbox):
    (sandbox / "code.py").write_text("FIXED_MARKER = True\n", encoding="utf-8")
    _write_debt(
        sandbox,
        "grep-absent-stale",
        "slug: grep-absent-stale\n"
        "title: fix marker now present\n"
        "date: 2026-05-31\n"
        "severity: low\n"
        "assert:\n"
        "  kind: grep_absent\n"
        "  file: code.py\n"
        "  pattern: FIXED_MARKER\n",
    )
    [st] = lib.compute_statuses()
    assert st.state == lib.STALE_FIXED


def test_grep_present_missing_file_is_stale(sandbox):
    """A grep_present target file that no longer exists ⇒ pattern absent ⇒ stale."""
    _write_debt(
        sandbox,
        "grep-missing-file",
        "slug: grep-missing-file\n"
        "title: tracked file deleted\n"
        "date: 2026-05-31\n"
        "severity: low\n"
        "assert:\n"
        "  kind: grep_present\n"
        "  file: gone.py\n"
        "  pattern: anything\n",
    )
    [st] = lib.compute_statuses()
    assert st.state == lib.STALE_FIXED


def test_script_open_when_predicate_true(sandbox):
    (sandbox / "pred.py").write_text("def still_open():\n    return True\n", encoding="utf-8")
    _write_debt(
        sandbox,
        "script-open",
        "slug: script-open\n"
        "title: predicate says still open\n"
        "date: 2026-05-31\n"
        "severity: high\n"
        "assert:\n"
        "  kind: script\n"
        "  module: pred.py\n"
        "  predicate: still_open\n",
    )
    [st] = lib.compute_statuses()
    assert st.state == lib.OPEN


def test_script_stale_when_predicate_false(sandbox):
    (sandbox / "pred.py").write_text("def still_open():\n    return False\n", encoding="utf-8")
    _write_debt(
        sandbox,
        "script-stale",
        "slug: script-stale\n"
        "title: predicate says fixed\n"
        "date: 2026-05-31\n"
        "severity: medium\n"
        "assert:\n"
        "  kind: script\n"
        "  module: pred.py\n"
        "  predicate: still_open\n",
    )
    [st] = lib.compute_statuses()
    assert st.state == lib.STALE_FIXED


def test_script_error_is_invalid(sandbox):
    (sandbox / "pred.py").write_text("def boom():\n    raise RuntimeError('x')\n", encoding="utf-8")
    _write_debt(
        sandbox,
        "script-error",
        "slug: script-error\n"
        "title: predicate raises\n"
        "date: 2026-05-31\n"
        "severity: high\n"
        "assert:\n"
        "  kind: script\n"
        "  module: pred.py\n"
        "  predicate: boom\n",
    )
    [st] = lib.compute_statuses()
    assert st.state == lib.INVALID


def test_external_open_with_owner_and_trigger(sandbox):
    _write_debt(
        sandbox,
        "external-ok",
        "slug: external-ok\n"
        "title: inference SDK credential pending\n"
        "date: 2026-05-31\n"
        "severity: high\n"
        "owner: 推理平台\n"
        "trigger: SDK 凭据下发\n"
        "assert:\n"
        "  kind: external\n",
    )
    [st] = lib.compute_statuses()
    assert st.state == lib.OPEN
    assert st.owner == "推理平台"


def test_external_without_owner_is_invalid(sandbox):
    _write_debt(
        sandbox,
        "external-bad",
        "slug: external-bad\n"
        "title: external missing owner/trigger\n"
        "date: 2026-05-31\n"
        "severity: high\n"
        "assert:\n"
        "  kind: external\n",
    )
    [st] = lib.compute_statuses()
    assert st.state == lib.INVALID


def test_missing_required_field_is_invalid(sandbox):
    _write_debt(
        sandbox,
        "no-severity",
        "slug: no-severity\n"
        "title: missing severity\n"
        "date: 2026-05-31\n"
        "assert:\n"
        "  kind: grep_present\n"
        "  file: code.py\n"
        "  pattern: x\n",
    )
    [st] = lib.compute_statuses()
    assert st.state == lib.INVALID
    assert "severity" in st.detail


def test_bad_severity_is_invalid(sandbox):
    _write_debt(
        sandbox,
        "bad-severity",
        "slug: bad-severity\n"
        "title: bad severity value\n"
        "date: 2026-05-31\n"
        "severity: spicy\n"
        "assert:\n"
        "  kind: grep_present\n"
        "  file: code.py\n"
        "  pattern: x\n",
    )
    [st] = lib.compute_statuses()
    assert st.state == lib.INVALID


def test_unknown_assert_kind_is_invalid(sandbox):
    _write_debt(
        sandbox,
        "bad-kind",
        "slug: bad-kind\n"
        "title: unknown assert kind\n"
        "date: 2026-05-31\n"
        "severity: low\n"
        "assert:\n"
        "  kind: telepathy\n",
    )
    [st] = lib.compute_statuses()
    assert st.state == lib.INVALID
