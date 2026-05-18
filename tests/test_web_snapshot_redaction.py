from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from zw_brain.command.brain import BrainService
from zw_brain.domain.web_snapshot_redaction import redact_webui_snapshot
from zw_brain.shared.state_store import StateStore


def test_redact_r1_strips_capability_packages_but_keeps_delivery() -> None:
    """R1 still cannot see capability packages (cross-tenant integration concern),
    but the QUICKSTART R1 旅程 requires tracking 交付回执 / 异议 / 续期 against
    their own delivery tasks, so `delivery_tasks` is intentionally kept for R1
    after Phase 3. R3/R4 remain stripped (they only see workbench todos)."""
    with TemporaryDirectory() as tmp:
        store = StateStore(Path(tmp) / "state.json")
        svc = BrainService(state_store=store)
        full = svc.snapshot()
        out = redact_webui_snapshot(full, "r1")
        assert out["capability_packages"] == []
        assert len(full["capability_packages"]) > 0
        # R1 keeps delivery_tasks (Phase 3 — required by 看交付回执 surface)
        assert len(out["delivery_tasks"]) > 0
        # R3 / R4 still stripped — they only see workbench.todos
        for blocked in ("r3", "r4"):
            blocked_out = redact_webui_snapshot(full, blocked)
            assert blocked_out["delivery_tasks"] == [], f"{blocked} must not see raw delivery_tasks"


def test_redact_r7_keeps_capability_packages_others_lose_them() -> None:
    with TemporaryDirectory() as tmp:
        store = StateStore(Path(tmp) / "state.json")
        svc = BrainService(state_store=store)
        full = svc.snapshot()
        # Sanity: fixture must seed packages or the redaction decision below is vacuous.
        assert full["capability_packages"], "fixture seed must include capability packages"
        r7_out = redact_webui_snapshot(full, "r7")
        r3_out = redact_webui_snapshot(full, "r3")
        # R7 sees the original set (preservation, not just non-empty);
        # R3 sees an empty list (consistent with the R3/R4-as-blocked convention
        # used in test_redact_r1_strips_capability_packages_but_keeps_delivery).
        assert r7_out["capability_packages"] == full["capability_packages"]
        assert r3_out["capability_packages"] == []


def test_invoke_system_snapshot_uses_role_payload() -> None:
    with TemporaryDirectory() as tmp:
        store = StateStore(Path(tmp) / "state.json")
        svc = BrainService(state_store=store)
        snap_r1 = svc.invoke_skill("system.snapshot", {"role": "r1"})
        snap_r7 = svc.invoke_skill("system.snapshot", {"role": "r7"})
        assert snap_r1["capability_packages"] == []
        assert len(snap_r7["capability_packages"]) > 0
