"""Regression: dispute evidence replay must follow relatedRequestIds, not hardcoded demo REQ ids."""

from __future__ import annotations

from pathlib import Path

from tests._handler_call import call_handler
from zw_brain.command.brain import BrainService
from zw_brain.command.handlers.b1.audit import handler_audit_replay_evidence_chain
from zw_brain.shared.state_store import StateStore


def _brain_with_audit_events(tmp_path: Path, events: list[dict]) -> BrainService:
    # Fresh state file → clone_seed_snapshot(), not a stale local .data/brain_state.json.
    brain = BrainService(state_store=StateStore(path=tmp_path / "brain_state.json"))
    brain._snapshot["audit_events"] = events
    return brain


def _audit_event(*, event_id: str, target: str) -> dict:
    return {
        "id": event_id,
        "time": "04-25 09:00",
        "actor": "system",
        "type": "application.submit",
        "target": target,
        "result": "ok",
        "chain": "pending",
    }


def test_replay_evidence_chain_includes_dispute_related_request_ids(tmp_path: Path) -> None:
    """Demo dispute declares linked REQ ids; replay must pull their audit events."""
    brain = _brain_with_audit_events(
        tmp_path,
        [
            _audit_event(event_id="ae-linked-1", target="REQ-2026-04-25-0011"),
            _audit_event(event_id="ae-linked-2", target="REQ-2026-04-24-0007"),
            _audit_event(event_id="ae-unrelated", target="REQ-2026-04-26-9999"),
        ]
    )

    out = call_handler(
        handler_audit_replay_evidence_chain,
        brain=brain,
        skill_id="audit.replay_evidence_chain",
        payload={"dispute_id": "DSP-2026-04-25-0003"},
    )

    targets = {item["target"] for item in out["auditEvents"]}
    assert targets == {"REQ-2026-04-25-0011", "REQ-2026-04-24-0007"}


def test_replay_evidence_chain_without_related_request_ids_does_not_pull_demo_reqs(tmp_path: Path) -> None:
    """Non-demo disputes must not inherit parking-lot demo REQ ids into the evidence chain."""
    brain = _brain_with_audit_events(
        tmp_path,
        [
            _audit_event(event_id="ae-demo-req", target="REQ-2026-04-25-0011"),
            _audit_event(event_id="ae-dispute-only", target="DSP-2026-04-24-0006"),
        ]
    )

    out = call_handler(
        handler_audit_replay_evidence_chain,
        brain=brain,
        skill_id="audit.replay_evidence_chain",
        payload={"dispute_id": "DSP-2026-04-24-0006"},
    )

    targets = {item["target"] for item in out["auditEvents"]}
    assert "REQ-2026-04-25-0011" not in targets
    assert targets == {"DSP-2026-04-24-0006"}
