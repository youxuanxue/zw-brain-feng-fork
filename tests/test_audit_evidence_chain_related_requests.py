"""Regression: dispute evidence replay must follow relatedRequestIds, not hardcoded demo REQ ids."""

from __future__ import annotations

from pathlib import Path

from tests._handler_call import call_handler
from zw_brain.command.brain import BrainService
from zw_brain.command.handlers.b1.audit import handler_audit_replay_evidence_chain
from zw_brain.shared.state_store import StateStore


def _brain_with_audit_events(
    tmp_path: Path, events: list[dict], disputes: list[dict]
) -> BrainService:
    # Fresh state file → clone_seed_snapshot(), not a stale local .data/brain_state.json.
    # C-1 删演示单后 seed 无演示争议；本回归测试自带合成争议（声明 relatedRequestIds），
    # 不依赖已删的 DSP-2026-* 演示单，且不用 demo-id 字面（全仓零 demo id）。
    brain = BrainService(state_store=StateStore(path=tmp_path / "brain_state.json"))
    brain._snapshot["audit_events"] = events
    brain._snapshot["disputes"] = disputes
    return brain


def _dispute(*, dispute_id: str, related: list[str]) -> dict:
    return {
        "id": dispute_id,
        "title": "测试争议",
        "status": "open",
        "relatedRequestIds": related,
        "timeline": [],
        "aiSummary": {},
    }


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
    """Dispute declares linked request ids; replay must pull their audit events (data-driven)."""
    brain = _brain_with_audit_events(
        tmp_path,
        [
            _audit_event(event_id="ae-linked-1", target="REQ-TEST-LINK-A"),
            _audit_event(event_id="ae-linked-2", target="REQ-TEST-LINK-B"),
            _audit_event(event_id="ae-unrelated", target="REQ-TEST-OTHER"),
        ],
        disputes=[_dispute(dispute_id="DSP-TEST-1", related=["REQ-TEST-LINK-A", "REQ-TEST-LINK-B"])],
    )

    out = call_handler(
        handler_audit_replay_evidence_chain,
        brain=brain,
        skill_id="audit.replay_evidence_chain",
        payload={"dispute_id": "DSP-TEST-1"},
    )

    targets = {item["target"] for item in out["auditEvents"]}
    assert targets == {"REQ-TEST-LINK-A", "REQ-TEST-LINK-B"}


def test_replay_evidence_chain_without_related_request_ids_does_not_pull_unlinked_reqs(tmp_path: Path) -> None:
    """A dispute with no relatedRequestIds must not inherit unrelated request ids into the chain."""
    brain = _brain_with_audit_events(
        tmp_path,
        [
            _audit_event(event_id="ae-unlinked-req", target="REQ-TEST-LINK-A"),
            _audit_event(event_id="ae-dispute-only", target="DSP-TEST-2"),
        ],
        disputes=[_dispute(dispute_id="DSP-TEST-2", related=[])],
    )

    out = call_handler(
        handler_audit_replay_evidence_chain,
        brain=brain,
        skill_id="audit.replay_evidence_chain",
        payload={"dispute_id": "DSP-TEST-2"},
    )

    targets = {item["target"] for item in out["auditEvents"]}
    assert "REQ-TEST-LINK-A" not in targets
    assert targets == {"DSP-TEST-2"}
