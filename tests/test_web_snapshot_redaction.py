from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from zw_brain.command.brain import BrainService
from zw_brain.domain.web_snapshot_redaction import redact_webui_snapshot
from zw_brain.shared.state_store import StateStore


def test_redact_r1_strips_capability_packages_and_delivery() -> None:
    with TemporaryDirectory() as tmp:
        store = StateStore(Path(tmp) / "state.json")
        svc = BrainService(state_store=store)
        full = svc.snapshot()
        out = redact_webui_snapshot(full, "r1")
        assert out["capability_packages"] == []
        assert out["delivery_tasks"] == []
        assert len(full["capability_packages"]) > 0
        assert len(full["delivery_tasks"]) > 0


def test_redact_r7_keeps_capability_packages() -> None:
    with TemporaryDirectory() as tmp:
        store = StateStore(Path(tmp) / "state.json")
        svc = BrainService(state_store=store)
        full = svc.snapshot()
        out = redact_webui_snapshot(full, "r7")
        assert len(out["capability_packages"]) > 0


def test_invoke_system_snapshot_uses_role_payload() -> None:
    with TemporaryDirectory() as tmp:
        store = StateStore(Path(tmp) / "state.json")
        svc = BrainService(state_store=store)
        snap_r1 = svc.invoke_skill("system.snapshot", {"role": "r1"})
        snap_r7 = svc.invoke_skill("system.snapshot", {"role": "r7"})
        assert snap_r1["capability_packages"] == []
        assert len(snap_r7["capability_packages"]) > 0
