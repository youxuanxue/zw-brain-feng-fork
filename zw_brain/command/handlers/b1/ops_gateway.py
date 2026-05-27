"""B1 ops_gateway handlers — 2 cap migrated from BrainService (F1 turn 5).

Method bodies physically migrated (`self.` → `brain.`); per-cap handler functions
registered in `zw_brain.command.dispatch.DISPATCH_TABLE`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

import copy
from datetime import datetime

from zw_brain.command.brain import BrainServiceError
from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.command.serializers import ops_metrics as ops_metrics_ser

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _ingest_gateway_heartbeat(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    status = str(payload.get("status", "online"))
    if status not in {"online", "warning", "offline"}:
        raise BrainServiceError(f"unsupported gateway status: {status}")
    gateway_payload = {
        "gateway_instance_id": str(payload["gateway_instance_id"]),
        "gateway_address_ref": payload.get("gateway_address_ref"),
        "runtime_profile": payload.get("runtime_profile"),
        "status": status,
        "last_reported_at": payload.get("last_reported_at") or datetime.now().isoformat(),
        "source_ref": payload.get("source_ref") or "gateway-heartbeat",
        "summary_json": copy.deepcopy(payload.get("summary_json", {})),
    }

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        store = deps.state_store.database_store
        if store is None:
            statuses = deps.brain_legacy._snapshot.setdefault("gateway_runtime_statuses", [])
            current = next((item for item in statuses if item["gateway_instance_id"] == gateway_payload["gateway_instance_id"]), None)
            if current is None:
                current = copy.deepcopy(gateway_payload)
                statuses.append(current)
            else:
                current.update(copy.deepcopy(gateway_payload))
            result = copy.deepcopy(current)
        else:
            result = ops_metrics_ser.gateway_to_dict(deps.repos.gateway_runtime.upsert_heartbeat(gateway_payload))
        deps.append_audit_feed("ops.gateway.heartbeat", gateway_payload["gateway_instance_id"], "ok", actor)
        return result | {"audit_id": audit_id}

    return deps.write(ctx, gateway_payload, mutation)

def _anchor_gateway_log(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    gateway_log_ref = str(payload["gateway_log_ref"])
    evidence = brain._safe_json(payload.get("evidence_json", {}))
    anchor_payload = {
        "gateway_log_ref": gateway_log_ref,
        "resource_code": payload.get("resource_code"),
        "source_ref": payload.get("source_ref") or gateway_log_ref,
        "evidence_json": evidence,
    }

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        store = deps.state_store.database_store
        if store is not None:
            deps.repos.legacy_mapping.upsert_mapping(
                {
                    "source_ref": anchor_payload["source_ref"],
                    "legacy_object_ref": gateway_log_ref,
                    "canonical_type": "anchor_outbox",
                    "canonical_ref": audit_id,
                    "evidence_json": {"resource_code": anchor_payload.get("resource_code")},
                }
            )
        deps.append_audit_feed("ops.gateway.log.anchor", gateway_log_ref, "ok", actor)
        return anchor_payload | {"anchor_outbox_ref": audit_id, "audit_id": audit_id}

    return deps.write(ctx, anchor_payload, mutation)


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_ops_gateway_heartbeat_ingest(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _ingest_gateway_heartbeat(brain, deps, ctx, payload)

def handler_ops_gateway_log_anchor(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _anchor_gateway_log(brain, deps, ctx, payload)

