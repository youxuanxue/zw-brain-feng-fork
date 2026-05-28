"""Cross-cutting pipeline operations — Action E module-level helpers.

Background
----------
Before Action E, the 5 cross-cutting helpers (``_mutate`` / ``_invoke_traced_read`` /
``_emit_audit`` / ``_enqueue_anchor`` / ``_append_audit_feed``) lived as private
methods on ``BrainService``. ``SkillPipeline`` middlewares (Action B) called
them through a ``brain_legacy`` reference, which left BrainService as the
de-facto cross-cutting god-class even after Action D split the 7 domain
services out.

Action E lifts the cross-cutting bodies into module-level functions taking
explicit dependencies (state_store / audit_bus / queue / manifest_getter /
snapshot). Each function operates on the dependencies it actually needs —
no implicit ``self.brain`` backref. BrainService retains a one-line delegate
shim per migrated helper so legacy call sites (in-process scripts, test
fixtures) still work; preflight segment 48 enforces the shim shape.

What lives here
---------------
- ``run_mutation`` — replaces ``BrainService._mutate`` (Policy/Identity/Audit/
  CapabilityCall/Persist/Anchor middleware chain bookend).
- ``run_traced_read`` — replaces ``BrainService._invoke_traced_read``.
- ``emit_audit`` — replaces ``BrainService._emit_audit`` (10-branch payload
  enrichment preserved verbatim).
- ``enqueue_anchor`` — replaces ``BrainService._enqueue_anchor`` (fail-soft
  per D4: anchor failure must not poison mutation result).
- ``append_audit_feed`` — replaces ``BrainService._append_audit_feed`` (in-
  memory snapshot append for the B1 audit feed UI).

What stays in BrainService
--------------------------
- ``_sync_state_views`` / ``_persist`` / ``_sync_*`` — these read/write
  ``self._snapshot`` and ``self._ui_state``; lifting them out is tracked as
  the snapshot-model consolidation debt (docs/preflight-debt.md 2026-05-28).
  ``run_mutation`` here calls back into ``brain._sync_state_views`` /
  ``brain._persist`` (the Persist middleware boundary stays where Action B
  left it).
- ``_audit_decision_reason`` / ``_audit_target_from_payload`` — small pure
  helpers, kept module-private on BrainService; ``emit_audit`` receives
  pre-computed values from the middleware layer or accepts callable for
  lazy computation (see ``DecisionReasonFn`` / ``TargetRefFn`` types).
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from zw_brain.shared import ids
from zw_brain.shared.auth_context import get_auth_context
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID
from zw_brain.shared.sanitization import safe_json

if TYPE_CHECKING:
    from zw_brain.command.deps import SkillContext
    from zw_brain.command.pipeline import SkillPipeline
    from zw_brain.shared.state_store import StateStore


# ───────────────────────────────────────────────────────────────────────────
# Type aliases — handler functions and lazy helpers
# ───────────────────────────────────────────────────────────────────────────

# Manifest getter — caller supplies ``zw_brain.skill_registration.runtime.get_manifest``
ManifestGetter = Callable[[str], dict[str, Any]]
# Decision-reason resolver — phase + payload → decision reason string
DecisionReasonFn = Callable[[str, dict[str, Any]], str]
# Target-ref resolver — request_id + payload → target_ref string (snapshot keys)
TargetRefFn = Callable[[str, dict[str, Any]], str]
# Mutation closure same shape as BrainService._mutate / pipeline.HandlerFn
MutationFn = Callable[[str, str], dict[str, Any]]
# Generic operation closure for read path
ReadOperation = Callable[[], Any]


# ───────────────────────────────────────────────────────────────────────────
# emit_audit — replaces BrainService._emit_audit
# ───────────────────────────────────────────────────────────────────────────


def emit_audit(
    audit_bus: Any,
    manifest_getter: ManifestGetter,
    decision_reason_fn: DecisionReasonFn,
    target_ref_fn: TargetRefFn,
    request_id: str,
    actor: str,
    skill_id: str,
    phase: str,
    payload: dict[str, Any],
) -> None:
    """Emit a normalized audit event via ``audit_bus.emit``.

    Replaces ``BrainService._emit_audit``. Preserves all 10 branches of payload
    enrichment from the legacy body:

    1. ``payload_with_evidence = safe_json(payload)`` — strip trust sentinel.
    2. ``actor_snapshot`` from payload override OR derived from ``actor`` parts.
    3. ``role_code`` lifted from actor parts when actor matches ``user:gov:<role>``.
    4. ``development_iam_bypass`` flag mirrored onto both actor_snapshot + payload.
    5. ``skill_id`` always pinned to the canonical id.
    6. ``audit_class`` defaulted from manifest when payload lacks it.
    7. ``actor_snapshot`` written back into payload.
    8. ``policy_version`` defaulted from manifest version.
    9. ``decision_reason`` resolved via ``decision_reason_fn(phase, payload)``.
   10. ``target_ref`` resolved via ``target_ref_fn(request_id, payload)``.

    ``audit_bus`` is the ``zw_brain.shared.audit`` module (passed by caller so
    tests can stub it). ``manifest_getter`` is ``get_manifest`` from the
    skill_registration runtime (passed for the same reason).
    """
    manifest = manifest_getter(skill_id)
    actor_parts = actor.split(":", 3)
    payload_with_evidence = safe_json(payload)
    if isinstance(payload_with_evidence.get("actor_snapshot"), dict) and payload_with_evidence["actor_snapshot"]:
        actor_snapshot = copy.deepcopy(payload_with_evidence["actor_snapshot"])
    else:
        actor_snapshot = {"actor": actor}
        if len(actor_parts) >= 3 and actor_parts[:2] == ["user", "gov"]:
            actor_snapshot["role_code"] = actor_parts[2]
    ctx = get_auth_context()
    if ctx is not None and ctx.development_iam_bypass:
        actor_snapshot["development_iam_bypass"] = True
        payload_with_evidence["development_iam_bypass"] = True
    payload_with_evidence["skill_id"] = skill_id
    payload_with_evidence["audit_class"] = payload_with_evidence.get("audit_class") or manifest.get("audit_class")
    payload_with_evidence["actor_snapshot"] = actor_snapshot
    payload_with_evidence["policy_version"] = payload_with_evidence.get("policy_version") or manifest.get("version")
    payload_with_evidence["decision_reason"] = payload_with_evidence.get("decision_reason") or decision_reason_fn(phase, payload)
    payload_with_evidence["target_ref"] = payload_with_evidence.get("target_ref") or target_ref_fn(request_id, payload)
    audit_bus.emit(
        audit_bus.AuditEvent(
            request_id=request_id,
            actor=actor,
            skill_id=skill_id,
            phase=phase,
            payload=payload_with_evidence,
        )
    )


# ───────────────────────────────────────────────────────────────────────────
# record_capability_call — replaces BrainService._record_capability_call
# ───────────────────────────────────────────────────────────────────────────


def record_capability_call(
    state_store: StateStore,
    target_ref_fn: TargetRefFn,
    audit_id: str,
    actor: str,
    role: str,
    skill_id: str,
    payload: dict[str, Any],
    result: dict[str, Any],
    started_at: datetime,
    *,
    status: str = "succeeded",
) -> None:
    """Append a capability_call row to the audit DB.

    Replaces ``BrainService._record_capability_call``. ``state_store`` carries
    the database_store handle (None in legacy in-memory mode — silent skip).
    ``target_ref_fn`` defaults to ``default_target_ref`` when called from the
    BrainService shim; CapabilityCallMiddleware passes it explicitly.
    """
    store = state_store.database_store
    if store is None:
        return
    store.append_capability_call(
        {
            "call_ref": audit_id,
            "tenant_id": str(payload.get("tenant_id", _DEFAULT_TENANT_ID)),
            "skill_id": skill_id,
            "actor": actor,
            "role_code": role,
            "status": status,
            "request_ref": target_ref_fn(audit_id, payload),
            "input_json": safe_json(payload),
            "output_json": safe_json(result),
            "started_at": started_at,
            "completed_at": datetime.now(),
        }
    )


# ───────────────────────────────────────────────────────────────────────────
# enqueue_anchor — replaces BrainService._enqueue_anchor
# ───────────────────────────────────────────────────────────────────────────


def enqueue_anchor(
    queue: Any,
    state_store: StateStore,
    request_id: str,
    actor: str,
    skill_id: str,
    payload: dict[str, Any],
) -> None:
    """Compute content hash, write anchor_outbox row, enqueue blockchain anchor.

    Replaces ``BrainService._enqueue_anchor``. Fail-soft semantics live in
    the calling middleware (``AnchorMiddleware``) per D4 contract.

    ``queue`` is the ``zw_brain.shared.queue`` module (passed for testability).
    """
    # safe_json strips the trust sentinel and other process-local objects that
    # cannot cross a JSON boundary. Without it, the payload may carry the
    # _TRUSTED_SESSION_MARKER (object()) and json.dumps below raises TypeError.
    sanitized_payload = safe_json(payload)
    content_hash = hashlib.sha256(
        json.dumps(
            {
                "request_id": request_id,
                "actor": actor,
                "skill_id": skill_id,
                "payload": sanitized_payload,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    store = state_store.database_store
    if store is not None:
        store.append_anchor_outbox(request_id, skill_id, content_hash, "mock-chain")
    asyncio.run(
        queue.enqueue(
            "blockchain.anchor",
            {
                "request_id": request_id,
                "skill_id": skill_id,
                "actor": actor,
                "content_hash": content_hash,
                "chain_id": "mock-chain",
            },
        )
    )


# ───────────────────────────────────────────────────────────────────────────
# append_audit_feed — replaces BrainService._append_audit_feed
# ───────────────────────────────────────────────────────────────────────────


def append_audit_feed(
    snapshot: dict[str, Any],
    event_type: str,
    target: str,
    result: str,
    actor: str,
) -> None:
    """Append a row to the in-memory ``audit_events`` snapshot list.

    Replaces ``BrainService._append_audit_feed``. The B1 audit feed UI reads
    this list directly; the database audit_event table is written by
    ``audit_bus.emit`` independently — this function only updates the
    in-memory projection.
    """
    # Lazy import keeps the call cheap when the audit_events list is empty.
    from zw_brain.shared import clock  # noqa: PLC0415

    snapshot["audit_events"].append(
        {
            "id": ids.new_audit_id(),
            "time": clock.month_day_time(),
            "actor": actor,
            "type": event_type,
            "target": target,
            "result": result,
            "chain": "pending" if result != "failed" else "n/a",
        }
    )


# ───────────────────────────────────────────────────────────────────────────
# run_mutation / run_traced_read — replaces BrainService._mutate / _invoke_traced_read
# ───────────────────────────────────────────────────────────────────────────


def run_mutation(
    pipeline: SkillPipeline,
    ctx: SkillContext,
    payload: dict[str, Any],
    mutation: MutationFn,
) -> dict[str, Any]:
    """Route a write-path mutation through ``SkillPipeline.write``.

    Replaces ``BrainService._mutate``. The middleware chain (Policy →
    Identity → AuditEmit → CapabilityCall → Persist → Anchor) is already
    in place; this is a thin shape adapter so handler-side callers can
    drop the BrainService backref entirely.
    """
    return pipeline.write(ctx, payload, mutation)


def run_traced_read(
    pipeline: SkillPipeline,
    state_store: StateStore,
    ctx: SkillContext,
    payload: dict[str, Any],
    operation: ReadOperation,
) -> Any:
    """Route a read-path operation through ``SkillPipeline.read``.

    Replaces ``BrainService._invoke_traced_read``. Fallback: if no
    ``database_store`` is configured (legacy in-memory mode), skip the
    audit pipeline and run the operation directly — production / CI
    always have a database_store, so this branch is dev-only.
    """
    if state_store.database_store is None:
        return operation()
    return pipeline.read(ctx, payload, lambda _audit_id, _actor: operation())


# ───────────────────────────────────────────────────────────────────────────
# Default decision_reason / target_ref resolvers — used by BrainService shims.
# Action E preserves the legacy resolution logic verbatim; future cross-cuttings
# may pass alternate resolvers (e.g. to inject a different priority order for
# target_ref). Defaults match ``BrainService._audit_decision_reason`` and
# ``BrainService._audit_target_from_payload``.
# ───────────────────────────────────────────────────────────────────────────


def default_decision_reason(phase: str, payload: dict[str, Any]) -> str:
    """Default decision reason resolver — payload override or phase fallback."""
    value = payload.get("decision_reason") or payload.get("decision") or payload.get("error") or phase
    return str(value)


# Ordered list of payload keys that may carry a canonical target_ref. Order
# matches ``BrainService._audit_target_from_payload`` — never reorder; audit
# downstreams rely on this priority for trace_triangle / chain anchoring.
_TARGET_REF_KEYS: tuple[str, ...] = (
    "dispute_id",
    "request_id",
    "task_id",
    "package_id",
    "resource_id",
    "catalog_id",
    "catalog_code",
    "resource_code",
    "service_id",
    "zone_id",
    "target_ref",
    "id",
)


def default_target_ref(request_id: str, payload: dict[str, Any]) -> str:
    """Default target_ref resolver — first non-empty key from ``_TARGET_REF_KEYS``."""
    for fld in _TARGET_REF_KEYS:
        value = payload.get(fld)
        if value:
            return str(value)
    return request_id
