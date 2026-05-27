"""B1 ops_exchange handlers — 1 cap migrated from BrainService (F1 turn 5).

Method bodies physically migrated (`self.` → `brain.`); per-cap handler functions
registered in `zw_brain.command.dispatch.DISPATCH_TABLE`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService

from zw_brain.command.serializers import delivery as delivery_ser
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEFAULT_TENANT_ID = get_runtime_tenant_id()



# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _diagnose_exchange(brain, *, task_id: Any = None, attempt_id: Any = None) -> dict[str, Any]:
    delivery_code = str(task_id) if task_id else None
    attempt_code = str(attempt_id) if attempt_id else None
    attempts = [delivery_ser.delivery_attempt_to_dict(item) for item in brain._delivery_repo().list_attempts(delivery_code=delivery_code, attempt_code=attempt_code)]
    evidence = [delivery_ser.delivery_evidence_to_dict(item) for item in brain._delivery_repo().list_execution_evidence(delivery_code=delivery_code, attempt_code=attempt_code, tenant_id=_DEFAULT_TENANT_ID)]
    metrics = [delivery_ser.exchange_metric_to_dict(item) for item in brain._delivery_repo().list_exchange_metrics(delivery_code=delivery_code, tenant_id=_DEFAULT_TENANT_ID)]
    return {"attempts": attempts, "evidence": evidence, "metrics": metrics, "diagnosis": {"state": "failed" if any(item["state"] in {"failed", "stopped"} for item in attempts) else "observable"}}


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_ops_exchange_diagnose(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _diagnose_exchange(brain, task_id=payload.get("task_id"), attempt_id=payload.get("attempt_id"))

