"""B1 audit handlers — 2 cap migrated from BrainService (F1 turn 5).

Method bodies physically migrated (`self.` → `brain.`); per-cap handler functions
registered in `zw_brain.command.dispatch.DISPATCH_TABLE`.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService

from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEFAULT_TENANT_ID = get_runtime_tenant_id()

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _list_audit_events(brain) -> list[dict[str, Any]]:
    """Return audit timeline for 安全审计员 / dashboard.

    Time ordering: 内部分两 chunk —— 最近 500 条 audit_event（asc by time）
    + 最多 200 条 legacy.exchange.import projection（asc by mapped_at）。
    每个 chunk 内时序严格升序；两 chunk 之间不保证 interleave。安全审计员 UI 把
    legacy import 视作单独区段呈现，不与 audit 实时事件强混排。
    """
    store = brain._state_store.database_store
    if store is None:
        return copy.deepcopy(brain._snapshot["audit_events"])
    # 默认拉最近 500 条；早期是 SELECT * 拉 2000+ 行（含大 payload_json），
    # audit.list 与 compliance.case.query 撞 14-30s 慢。
    events = [
        {
            "id": item.request_id,
            "time": item.occurred_at.strftime("%m-%d %H:%M"),
            "actor": item.actor,
            "type": f"{item.skill_id}.{item.phase}",
            "target": brain._audit_event_target(item),
            "result": "ok",
            "chain": "pending",
        }
        for item in store.list_audit_events(limit=500)
    ]
    # Push filter into SQL: 不要拉 54K mappings 全部到 Python 再过滤；只取 audit-relevant 三类 + cap 200。
    for mapping in store.legacy_mapping_repo.list_mappings(
        tenant_id=_DEFAULT_TENANT_ID,
        legacy_object_types=["data_apply", "data_apply_course", "data_apply_authrization"],
        limit=200,
    ):
        events.append(
            {
                "id": mapping.id,
                "time": mapping.mapped_at.strftime("%m-%d %H:%M"),
                "actor": "legacy.exchange.import",
                "type": f"legacy.exchange.import.{mapping.legacy_object_type}",
                "target": mapping.legacy_object_ref,
                "result": mapping.mapping_status,
                "chain": f"{mapping.legacy_object_type}->{mapping.canonical_type}",
            }
        )
    return events

def _replay_evidence_chain(brain, dispute_id: str) -> dict[str, Any]:
    dispute = brain.get_dispute(dispute_id)
    evidence = [
        {
            "time": step.get("time") or step.get("payload", {}).get("time") or "—",
            "label": step.get("label") or step.get("nodeName") or "证据",
            "detail": step.get("note") or step.get("opinion") or "—",
        }
        for step in dispute.get("timeline", [])
    ]
    audit_events = [
        item
        for item in brain.list_audit_events()
        if item["target"] in {dispute_id, "REQ-2026-04-24-0007", "REQ-2026-04-25-0011"}
    ]
    return {
        "disputeId": dispute_id,
        "summary": dispute.get("aiSummary"),
        "evidenceChain": evidence,
        "auditEvents": audit_events,
        "tickets": [item for item in brain._snapshot["tickets"] if item["id"] in {"TK-2026-04-25-014", "TK-2026-04-25-015"}],
        "knowledgeArticles": [item for item in brain._snapshot["knowledge_articles"] if item["id"] in {"KB-REDUCE-BURDEN-02", "KB-TEMPLATE-BACKFLOW-01"}],
    }


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_audit_list(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return {
        "items": _list_audit_events(brain),
        "summary": copy.deepcopy(brain._snapshot["audit_ai"]),
    }

def handler_audit_replay_evidence_chain(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _replay_evidence_chain(brain, str(payload["dispute_id"]))

