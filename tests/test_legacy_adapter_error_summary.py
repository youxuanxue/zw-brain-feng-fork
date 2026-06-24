"""Silent-swallow ban: AdapterRunRecord.error_summary contract.

CLAUDE.md §2 全局宪法 禁止 silent error swallow. `legacy.bsp.governance` adapter
historically left `adapter_run_record.error_summary = None` when missing_manifest
rows were business-level fail-closed (governance.py:141), turning the receipt
opaque. This test pins the post-fix invariants:

1. `ImportStats.add_issue` accepts `severity` ∈ {"error", "warn"}, default "error".
2. warn-severity issues do NOT bump `failure_count` and the run stays "succeeded".
3. error_summary is populated whenever any issue exists (errors OR warns), so
   the receipt is never silent.
4. error-severity issues DO bump `failure_count` → status = "partial_failure".

Together these unlock customer_acceptance_up.sh non-strict path on real dumps.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from zw_brain.adapters.legacy._common import ImportStats, finish_run
from zw_brain.domain.repositories.external_adapter import ExternalAdapterRepository
from zw_brain.shared.migrate import ensure_runtime_schema


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    ensure_runtime_schema()
    return tmp_path


def _make_stats(dump: str) -> ImportStats:
    return ImportStats(schema="dsp_bsp", dump_path=Path(dump))


@pytest.mark.no_db
def test_add_issue_rejects_unknown_severity() -> None:
    stats = _make_stats("dump-dsp_bsp-x.sql")
    with pytest.raises(ValueError, match="severity"):
        stats.add_issue("x", "y", "z", severity="banana")  # type: ignore[arg-type]


@pytest.mark.no_db
def test_add_issue_records_severity_field() -> None:
    stats = _make_stats("dump-dsp_bsp-x.sql")
    stats.add_issue("missing_manifest", "pub_user_role", "", severity="warn")
    stats.add_issue("missing_actor_ref", "sys_user", "1")  # default error
    assert stats.issues[0]["severity"] == "warn"
    assert stats.issues[1]["severity"] == "error"


def test_clean_run_has_no_error_summary(temp_db: Path) -> None:
    """A run with zero issues / zero errors leaves error_summary as None."""
    stats = _make_stats("dump-dsp_bsp-clean.sql")
    stats.bump("pub_organ")
    finish_run(
        ExternalAdapterRepository(),
        stats,
        adapter_slug="legacy.bsp.test_clean",
        dump_path=Path("dump-dsp_bsp-clean.sql"),
        started_at=datetime.now(UTC),
        tenant_id="sd-default",
    )
    runs = {r.adapter_slug: r for r in ExternalAdapterRepository().list_run_records(tenant_id="sd-default")}
    rec = runs["legacy.bsp.test_clean"]
    assert rec.status == "succeeded"
    assert rec.failure_count == 0
    assert rec.error_summary is None


def test_warn_only_run_stays_succeeded_with_non_null_error_summary(temp_db: Path) -> None:
    """missing_manifest fail-closed case: status stays succeeded, error_summary is non-None.

    This is the exact scenario governance.py:141 hits on real customer dumps and
    why `customer_acceptance_up.sh --strict` used to be unrunnable on real
    dumps. Post-fix the run is "succeeded" so strict mode doesn't break.
    """
    stats = _make_stats("dump-dsp_bsp-warn.sql")
    stats.bump("pub_user")
    stats.add_issue(
        "missing_manifest",
        "pub_user_role",
        "",
        {"row_count": 100, "reason": "pub_governance_relation_requires_manifest"},
        severity="warn",
    )
    finish_run(
        ExternalAdapterRepository(),
        stats,
        adapter_slug="legacy.bsp.test_warn",
        dump_path=Path("dump-dsp_bsp-warn.sql"),
        started_at=datetime.now(UTC),
        tenant_id="sd-default",
    )
    runs = {r.adapter_slug: r for r in ExternalAdapterRepository().list_run_records(tenant_id="sd-default")}
    rec = runs["legacy.bsp.test_warn"]
    assert rec.status == "succeeded", f"warn-only run must NOT be partial_failure: got {rec.status}"
    assert rec.failure_count == 0
    assert rec.error_summary is not None, "CLAUDE.md §2: error_summary cannot be None when issues exist"
    assert "business_skips: 1" in rec.error_summary
    assert "pub_user_role.missing_manifest=1" in rec.error_summary
    assert "technical_errors: 0" in rec.error_summary


def test_error_severity_bumps_run_to_partial_failure(temp_db: Path) -> None:
    """Genuine data-corruption issues stay error-severity and produce partial_failure."""
    stats = _make_stats("dump-dsp_bsp-err.sql")
    stats.bump("sys_user")
    stats.add_issue("missing_actor_ref", "sys_user", "x", {"reason": "missing_user_id"})  # default error
    finish_run(
        ExternalAdapterRepository(),
        stats,
        adapter_slug="legacy.bsp.test_err",
        dump_path=Path("dump-dsp_bsp-err.sql"),
        started_at=datetime.now(UTC),
        tenant_id="sd-default",
    )
    runs = {r.adapter_slug: r for r in ExternalAdapterRepository().list_run_records(tenant_id="sd-default")}
    rec = runs["legacy.bsp.test_err"]
    assert rec.status == "partial_failure"
    assert rec.failure_count == 1
    assert rec.error_summary is not None
    assert "technical_errors: 1" in rec.error_summary
    assert "sys_user.missing_actor_ref=1" in rec.error_summary


def test_mixed_severities_split_correctly(temp_db: Path) -> None:
    """Both errors and warns at once: status = partial_failure (errors win), summary has both lines."""
    stats = _make_stats("dump-dsp_bsp-mixed.sql")
    stats.bump("sys_user")
    stats.add_issue("missing_actor_ref", "sys_user", "x")  # error
    stats.add_issue("missing_manifest", "pub_user_role", "", severity="warn")  # warn
    finish_run(
        ExternalAdapterRepository(),
        stats,
        adapter_slug="legacy.bsp.test_mixed",
        dump_path=Path("dump-dsp_bsp-mixed.sql"),
        started_at=datetime.now(UTC),
        tenant_id="sd-default",
    )
    runs = {r.adapter_slug: r for r in ExternalAdapterRepository().list_run_records(tenant_id="sd-default")}
    rec = runs["legacy.bsp.test_mixed"]
    assert rec.status == "partial_failure"
    assert "technical_errors: 1" in rec.error_summary
    assert "business_skips: 1" in rec.error_summary
