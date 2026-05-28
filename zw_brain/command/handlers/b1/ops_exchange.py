"""B1 ops_exchange handlers — 1 cap migrated from BrainService (F1 turn 5).

Method bodies physically migrated (`self.` → `brain.`); per-cap handler functions
registered in `zw_brain.command.dispatch.DISPATCH_TABLE`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.command.serializers import delivery as delivery_ser
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _diagnose_exchange(brain, deps, ctx, *, task_id: Any = None, attempt_id: Any = None) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    delivery_code = str(task_id) if task_id else None
    attempt_code = str(attempt_id) if attempt_id else None
    attempts = [delivery_ser.delivery_attempt_to_dict(item) for item in deps.repos.delivery.list_attempts(delivery_code=delivery_code, attempt_code=attempt_code)]
    evidence = [delivery_ser.delivery_evidence_to_dict(item) for item in deps.repos.delivery.list_execution_evidence(delivery_code=delivery_code, attempt_code=attempt_code, tenant_id=_DEFAULT_TENANT_ID)]
    metrics = [delivery_ser.exchange_metric_to_dict(item) for item in deps.repos.delivery.list_exchange_metrics(delivery_code=delivery_code, tenant_id=_DEFAULT_TENANT_ID)]
    return {"attempts": attempts, "evidence": evidence, "metrics": metrics, "diagnosis": {"state": "failed" if any(item["state"] in {"failed", "stopped"} for item in attempts) else "observable"}}


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_ops_exchange_diagnose(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _diagnose_exchange(brain, deps, ctx, task_id=payload.get("task_id"), attempt_id=payload.get("attempt_id"))

