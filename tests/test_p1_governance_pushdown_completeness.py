"""P1-2: governance audit/import-issues query pushdown + 500-cap completeness.

Two defects in GovernanceService:
1. `audit_events` loaded `list_audit_events()` (default LIMIT 500) then filtered the fixed
   governance skill_id whitelist in Python — so once audit_event exceeds 500 rows, a
   matching *older* governance event is silently truncated away (completeness defect, not
   just perf).
2. `import_issues` hydrated the *whole* unbounded capability_call table then filtered one
   skill_id in Python (perf defect on a runtime-accumulating table).

Fix: push the skill_id filter to SQL WHERE (indexed column) so LIMIT applies after the
filter / the table is never fully hydrated. Response shape unchanged.

These tests build >500 audit rows with one buried whitelisted match and assert it survives.
Against the pre-fix code the match is dropped → FAIL.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest


@pytest.fixture()
def temp_store(tmp_path, monkeypatch):
    """Isolated empty DB store (no seed) — pure store/service-layer coverage."""
    db_path = tmp_path / "p1_governance.db"
    monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
    monkeypatch.delenv("ZW_BRAIN_DATABASE_URL", raising=False)
    from zw_brain.shared import db as _db
    with _db._CACHE_LOCK:
        _db._ENGINE_CACHE.clear()
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.migrate import ensure_runtime_schema

    store = DatabaseStore()
    store.initialize()
    ensure_runtime_schema()  # creates runtime tables (audit_event / capability_call)
    yield store
    with _db._CACHE_LOCK:
        _db._ENGINE_CACHE.clear()


_WHITELISTED = "governance.iam_overview"
_NOISE = "workbench.view"  # not in the governance whitelist


def _seed_audit(store, *, buried_match_count: int = 3, noise_count: int = 600) -> None:
    """Insert whitelisted governance events as the OLDEST rows, then bury them under
    `noise_count` strictly-newer non-whitelisted events (> the 500 default cap).

    Timestamps are set explicitly + strictly increasing so the matches are deterministically
    outside any most-recent-500 window (no reliance on insertion-time tie-breaking).
    """
    from zw_brain.domain.models import AuditEventRecord

    base = datetime(2026, 1, 1, tzinfo=UTC)
    SessionLocal = store._session_factory()
    with SessionLocal() as session:
        ts = base
        # Oldest rows = the whitelisted matches we must not lose.
        for i in range(buried_match_count):
            session.add(AuditEventRecord(
                request_id=f"req-match-{i}", actor="actor-gov", skill_id=_WHITELISTED,
                phase="ok", payload_json={"tenant_id": "sd-default", "capability_id": "iam"},
                occurred_at=ts,
            ))
            ts += timedelta(seconds=1)
        # Newer noise rows so a naive 500-cap-then-filter drops the matches above.
        for i in range(noise_count):
            session.add(AuditEventRecord(
                request_id=f"req-noise-{i}", actor="actor-x", skill_id=_NOISE,
                phase="ok", payload_json={"tenant_id": "sd-default"},
                occurred_at=ts,
            ))
            ts += timedelta(seconds=1)
        session.commit()


def test_audit_events_completeness_under_500_cap(temp_store, monkeypatch):
    """A whitelisted governance audit event older than 500 newer noise rows must still be
    returned — the 500 cap may not truncate matches before the whitelist filter."""
    _seed_audit(temp_store, buried_match_count=3, noise_count=600)
    assert temp_store.count_audit_events() > 500

    # Drive through the real GovernanceService against this store.
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.state_store import StateStore

    brain = BrainService(state_store=StateStore(database_store=temp_store))
    events = brain._governance_audit_events(tenant_id="sd-default")

    matched = [e for e in events if e["skill_id"] == _WHITELISTED]
    assert len(matched) == 3, (
        f"expected all 3 buried whitelisted matches, got {len(matched)} — "
        "500-cap truncated matches before the whitelist filter (completeness defect)"
    )
    # Response shape unchanged: each event keeps the documented keys.
    for e in matched:
        assert set(e) >= {"id", "skill_id", "phase", "actor", "occurred_at", "payload_json"}


def test_audit_events_only_whitelisted_skills(temp_store):
    """Non-whitelisted skills must never appear (pushdown semantics == old Python filter)."""
    _seed_audit(temp_store, buried_match_count=2, noise_count=50)
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.state_store import StateStore

    brain = BrainService(state_store=StateStore(database_store=temp_store))
    events = brain._governance_audit_events(tenant_id="sd-default")
    assert all(e["skill_id"] != _NOISE for e in events)
    assert {e["skill_id"] for e in events} == {_WHITELISTED}


def test_capability_calls_by_skill_pushdown(temp_store):
    """import_issues pushdown returns only the matching skill_id, bounded — equivalence
    with the old full-scan + Python filter (minus the full hydration cost)."""
    # Two import calls + noise calls under other skill_ids.
    for i in range(3):
        temp_store.append_capability_call(
            {
                "call_ref": f"imp-{i}",
                "tenant_id": "sd-default",
                "skill_id": "legacy.bsp.mapping.import",
                "actor": "sys",
                "role_code": "ROLE_ORGAN_OPERATER",
                "status": "ok",
                "input_json": {},
                "output_json": {"items": [{"reason": "unmatched_role", "legacy_permission_ref": f"p{i}"}]},
            }
        )
    for i in range(5):
        temp_store.append_capability_call(
            {
                "call_ref": f"noise-{i}",
                "tenant_id": "sd-default",
                "skill_id": "workbench.view",
                "actor": "sys",
                "role_code": "ROLE_ORGAN_OPERATER",
                "status": "ok",
                "input_json": {},
                "output_json": {},
            }
        )
    calls = temp_store.list_capability_calls_for_capability("legacy.bsp.mapping.import")
    assert len(calls) == 3
    assert all(c.skill_id == "legacy.bsp.mapping.import" for c in calls)
