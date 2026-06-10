"""SkillPipeline — Action B middleware chain replacing BrainService._mutate /
_invoke_traced_read closure pipeline.

Background
----------
Before Action B, every write-path handler followed this pattern::

    def handler_X(deps, ctx, payload):
        brain = deps.brain_legacy
        role = ctx.role
        confirmed = bool(payload.get("confirmed"))

        def mutation(audit_id: str, actor: str) -> dict:
            record = repo.write(...)
            brain._append_audit_feed(event_type, target, "ok", actor)
            return {"record": record, "audit_id": audit_id}

        return brain._mutate("skill.id", role, confirmed, payload, mutation)

The ``_mutate`` body inside BrainService monolithically combined six concerns:
manifest policy enforcement, identity resolution (audit_id + actor), audit
emit before/after/error, capability_call DB row, snapshot persist, and the
blockchain anchor for side-effect skills. Adding a new cross-cutting (rate
limit / OTLP tracing / circuit breaker / metrics) required editing the
god-class.

Action B re-expresses the same pipeline as an ordered middleware chain
that handlers invoke via ``deps.pipeline.write(ctx, payload, fn)``. Adding
a new cross-cutting becomes a new ``Middleware`` subclass + an entry in
the registration order — zero edits to BrainService.

Middleware order is fixed and machine-verified by preflight segment 42
(``scripts/check_pipeline_middleware_order.py``):

    1. CapabilityLogMiddleware  — troubleshooting log (duration/outcome); transparent
    2. PolicyMiddleware         — enforce manifest policy + confirmation gate
    3. IdentityMiddleware       — resolve actor + mint audit_id, freeze into ctx
    4. AuditEmitMiddleware      — emit before/after/error audit events
    5. CapabilityCallMiddleware — append capability_call row to DB
    6. PersistMiddleware        — sync_state_views + persist (write-path only)
    7. AnchorMiddleware         — blockchain anchor outbox (side_effects only)

The chain has two entry shapes:

- ``pipeline.write(ctx, payload, fn)`` — full chain (mutation + persist + anchor)
- ``pipeline.read(ctx, payload, fn)`` — chain skipping Persist + Anchor (audit-only)

Action E middleware dependency model
------------------------------------
Before Action E each middleware held a ``self._brain`` reference and delegated
the actual operation through BrainService methods. Action E lifts the
cross-cutting bodies into ``zw_brain.command.pipeline_ops`` and re-types each
middleware around the minimum surface it actually needs:

- ``PolicyMiddleware``: keeps ``brain`` (calls ``_enforce_manifest_policy`` —
  domain-bound; lives on BrainService until policy.enforce_manifest_policy gains
  the AccessDeniedError translation).
- ``IdentityMiddleware``: keeps ``brain`` (calls ``_actor_for_role`` — depends
  on ``policy.actor_for_role`` + ``auth_context``).
- ``AuditEmitMiddleware``: drops brain; takes ``audit_bus`` + ``manifest_getter``
  + ``decision_reason_fn`` + ``target_ref_fn``; routes through ``pipeline_ops.emit_audit``.
- ``CapabilityCallMiddleware``: drops brain; takes ``state_store`` + ``target_ref_fn``;
  routes through ``pipeline_ops.record_capability_call``.
- ``PersistMiddleware``: keeps ``brain`` (``_sync_state_views`` + ``_persist`` —
  snapshot-model consolidation debt — docs/preflight-debt.md 2026-05-28;
  demo_state_sync coupling).
- ``AnchorMiddleware``: keeps ``brain`` (``_sync_database_aggregates`` reads
  ``self._snapshot``) PLUS takes ``state_store`` + ``queue`` for ``pipeline_ops.enqueue_anchor``.

``build_default_pipeline(brain)`` materializes the explicit deps from the
brain instance once at HandlerDeps construction — this remains the single
brain-touching factory.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from threading import RLock
from typing import TYPE_CHECKING, Any, Protocol

from zw_brain.command import pipeline_ops

if TYPE_CHECKING:
    from zw_brain.command.deps import SkillContext
    from zw_brain.shared.state_store import StateStore


# Innermost function the handler provides. (audit_id, actor) → result dict.
HandlerFn = Callable[[str, str], dict[str, Any]]


@dataclass
class PipelineContext:
    """Per-call execution context threaded through the middleware chain.

    **Intentionally mutable** — this is an internal middleware scratchpad,
    *not* part of the handler-facing API. ``IdentityMiddleware`` writes
    ``audit_id`` / ``actor`` during execution; threading a frozen ctx through
    the chain would require ``dataclasses.replace`` at every middleware boundary,
    which adds boilerplate without changing observable semantics.

    Contrast with ``HandlerDeps`` / ``SkillContext`` / ``Repos`` in
    ``zw_brain/command/deps.py``: those are the **handler-facing** dependency
    container + per-call identity, all ``frozen=True`` to prevent accidental
    mutation. ``tests/test_handler_dataclass_frozen_invariant.py`` enforces
    that frozen contract — if you add a new field to that public surface,
    keep it frozen. ``PipelineContext`` is explicitly exempt.
    """
    skill: SkillContext
    payload: dict[str, Any]
    is_write: bool
    # filled by IdentityMiddleware
    audit_id: str = ""
    actor: str = ""
    started_at: datetime = field(default_factory=datetime.now)


# ───────────────────────────────────────────────────────────────────────────
# Middleware protocol
# ───────────────────────────────────────────────────────────────────────────

NextFn = Callable[[PipelineContext], dict[str, Any]]


class Middleware(Protocol):
    """Single concern wrapping handler execution.

    ``next(pctx)`` invokes the rest of the chain (eventually the handler fn).
    Re-raise exceptions; do not swallow. Middlewares may augment ``pctx``
    before calling next and may post-process the returned dict.
    """
    def __call__(self, pctx: PipelineContext, next_: NextFn) -> dict[str, Any]: ...


# ───────────────────────────────────────────────────────────────────────────
# Concrete middlewares — Action E re-typed dependency surface.
# ───────────────────────────────────────────────────────────────────────────


_CAP_LOGGER = logging.getLogger("zw_brain.command.capability")


class CapabilityLogMiddleware:
    """Troubleshooting observability — one log line per capability call (duration/outcome).

    Strictly separate from ``AuditEmitMiddleware``: audit events are the durable
    compliance record (D4, sink failure熔断), this line is a best-effort log that
    may be lost. MUST stay transparent — exceptions re-raise unchanged, so an
    audit-bus failure raised by inner middlewares passes through merely observed
    (段 7a: never downgrade that raise to a log). Outermost on purpose: policy
    rejections, confirmation gates and audit熔断 all get a duration + outcome
    line. Logs metadata only — never payload/result bodies (redaction red line).
    """

    def __call__(self, pctx: PipelineContext, next_: NextFn) -> dict[str, Any]:
        started = time.monotonic()
        try:
            result = next_(pctx)
        except Exception as exc:
            self._log(pctx, f"error:{exc.__class__.__name__}", started)
            raise
        self._log(pctx, "ok", started)
        return result

    @staticmethod
    def _log(pctx: PipelineContext, outcome: str, started: float) -> None:
        actor = pctx.actor
        if not actor:
            # Failure before IdentityMiddleware (e.g. policy rejection) — fall back
            # to the verified request identity so the line is still attributable.
            from zw_brain.shared.auth_context import get_auth_context  # noqa: PLC0415

            ctx = get_auth_context()
            actor = ctx.username if ctx is not None else ""
        _CAP_LOGGER.info(
            "capability %s %s",
            pctx.skill.skill_id,
            outcome,
            extra={
                "event": "capability_call",
                "skill_id": pctx.skill.skill_id,
                "is_write": pctx.is_write,
                "outcome": outcome,
                "audit_id": pctx.audit_id,
                "actor": actor,
                "duration_ms": round((time.monotonic() - started) * 1000, 1),
            },
        )


class PolicyMiddleware:
    """Enforce manifest policy + human_confirmation_required gate.

    Replaces the ``_enforce_manifest_policy(...) + ConfirmationRequiredError``
    block at the top of ``BrainService._mutate``. Read-only ``pipeline.read``
    path already had policy enforced by ``invoke_skill`` before dispatch, so
    this middleware short-circuits on ``not pctx.is_write``.

    Holds ``brain`` because ``_enforce_manifest_policy`` translates the domain
    ``DomainAccessDeniedError`` into the BrainService-exported
    ``AccessDeniedError`` (kept stable for API consumers); lifting the
    translation into policy is part of the snapshot-model consolidation debt
    (docs/preflight-debt.md 2026-05-28).
    """
    def __init__(self, brain: Any) -> None:
        self._brain = brain

    def __call__(self, pctx: PipelineContext, next_: NextFn) -> dict[str, Any]:
        if pctx.is_write:
            manifest = pctx.skill.manifest
            self._brain._enforce_manifest_policy(
                pctx.skill.skill_id, manifest, pctx.skill.role,
                pctx.payload | {"confirmed": pctx.skill.confirmed},
            )
            if manifest.get("human_confirmation_required") and not pctx.skill.confirmed:
                from zw_brain.domain.errors import ConfirmationRequiredError  # noqa: PLC0415
                raise ConfirmationRequiredError(pctx.skill.skill_id)
        return next_(pctx)


class IdentityMiddleware:
    """Resolve actor + mint audit_id; freeze into PipelineContext.

    Centralizes what was previously the first three lines of both _mutate
    and _invoke_traced_read::

        actor = self._actor_for_role(role)
        audit_id = ids.new_audit_id()
        started_at = datetime.now()

    Holds ``brain`` because ``_actor_for_role`` resolves through
    ``policy.actor_for_role`` *plus* applies the auth_context dev-IAM-bypass
    suffix; pulling the suffix logic out is part of the snapshot-model
    consolidation debt (docs/preflight-debt.md 2026-05-28).
    """
    def __init__(self, brain: Any) -> None:
        self._brain = brain

    def __call__(self, pctx: PipelineContext, next_: NextFn) -> dict[str, Any]:
        from zw_brain.shared import ids  # noqa: PLC0415
        pctx.actor = self._brain._actor_for_role(pctx.skill.role)
        pctx.audit_id = ids.new_audit_id()
        pctx.started_at = datetime.now()
        return next_(pctx)


class AuditEmitMiddleware:
    """Emit before / after / error audit events via the audit bus.

    Wraps the handler call in try/except — replaces the body of both
    ``_mutate`` and ``_invoke_traced_read`` between the identity step and
    the persist step. The 10-branch payload enrichment lives in
    ``pipeline_ops.emit_audit``; this middleware only sequences the phase
    calls. Action E dropped the ``brain`` reference: ``audit_bus`` +
    ``manifest_getter`` + the two resolver callables are sufficient.
    """
    def __init__(
        self,
        audit_bus: Any,
        manifest_getter: pipeline_ops.ManifestGetter,
        decision_reason_fn: pipeline_ops.DecisionReasonFn,
        target_ref_fn: pipeline_ops.TargetRefFn,
    ) -> None:
        self._audit_bus = audit_bus
        self._manifest_getter = manifest_getter
        self._decision_reason_fn = decision_reason_fn
        self._target_ref_fn = target_ref_fn

    def __call__(self, pctx: PipelineContext, next_: NextFn) -> dict[str, Any]:
        self._emit(pctx, "before", pctx.payload)
        try:
            result = next_(pctx)
        except Exception as exc:
            self._emit(
                pctx, "error",
                {"error": exc.__class__.__name__, "message": str(exc)},
            )
            raise
        # ``result`` may be a non-dict (read-only skills sometimes return list).
        after_payload = result if isinstance(result, dict) else {"result": result}
        self._emit(pctx, "after", after_payload)
        return result

    def _emit(self, pctx: PipelineContext, phase: str, payload: dict[str, Any]) -> None:
        # mcp-hardening S2: ``source`` is request-scoped provenance — it must be stamped
        # on EVERY phase (before/after/error), not just the phases whose payload happens
        # to be the original request payload. The 'after' phase payload is the handler's
        # result dict (no source), so inject it from the call-scoped SkillContext here.
        if pctx.skill.source and "source" not in payload:
            payload = {**payload, "source": pctx.skill.source}
        pipeline_ops.emit_audit(
            self._audit_bus, self._manifest_getter,
            self._decision_reason_fn, self._target_ref_fn,
            pctx.audit_id, pctx.actor, pctx.skill.skill_id, phase, payload,
        )


class CapabilityCallMiddleware:
    """Append the capability_call DB row (success or failed).

    Wraps next_() so that failure also records — replaces the explicit
    ``_record_capability_call(..., status="failed")`` in the except clause
    of _mutate / _invoke_traced_read. Action E routes through
    ``pipeline_ops.record_capability_call``; the middleware no longer
    needs a brain reference.
    """
    def __init__(
        self,
        state_store: StateStore,
        target_ref_fn: pipeline_ops.TargetRefFn,
    ) -> None:
        self._state_store = state_store
        self._target_ref_fn = target_ref_fn

    def __call__(self, pctx: PipelineContext, next_: NextFn) -> dict[str, Any]:
        try:
            result = next_(pctx)
        except Exception as exc:
            pipeline_ops.record_capability_call(
                self._state_store, self._target_ref_fn,
                pctx.audit_id, pctx.actor, pctx.skill.role, pctx.skill.skill_id,
                pctx.payload,
                {"error": exc.__class__.__name__, "message": str(exc)},
                pctx.started_at, status="failed",
            )
            raise
        record_payload = result if isinstance(result, dict) else {"result": result}
        pipeline_ops.record_capability_call(
            self._state_store, self._target_ref_fn,
            pctx.audit_id, pctx.actor, pctx.skill.role, pctx.skill.skill_id,
            pctx.payload, record_payload, pctx.started_at,
        )
        return result


class PersistMiddleware:
    """``sync_state_views`` + ``persist`` after a successful mutation.

    Read path skips this middleware entirely (no snapshot changes to persist).

    Holds ``brain`` because the BrainService instance is the lifecycle owner
    of ``_snapshot`` / ``_ui_state`` / ``_state_store``. Action H: the
    ``sync_state_views`` / ``persist`` module-level functions take explicit
    dependencies (snapshot dict + status_text callback + state_store) and no
    longer reach back into BrainService — middleware passes them through
    explicitly.
    """
    def __init__(self, brain: Any) -> None:
        self._brain = brain

    def __call__(self, pctx: PipelineContext, next_: NextFn) -> dict[str, Any]:
        result = next_(pctx)
        if pctx.is_write:
            # Action H: call sync module-level fns with explicit deps; the
            # legacy shims on BrainService still work but going through them
            # would defeat the point of the decoupling.
            from zw_brain.command import sync as state_sync  # noqa: PLC0415
            status_text = self._brain._get_handler_deps().services.request.status_text
            state_sync.sync_state_views(self._brain._snapshot, status_text)
            state_sync.persist(
                self._brain._state_store,
                self._brain._snapshot,
                self._brain._ui_state.persistable_view(),
            )
        return result


class AnchorMiddleware:
    """Sync database aggregates + enqueue blockchain anchor for ``side_effects`` skills.

    Mutation-only and side-effects-only — both read path and non-side-effect
    writes skip the heavy lifting.

    Fail-soft per docs/approved/zw-brain-architecture.md D4: "审计总线强制同步落库；
    区块链锚定通过可插拔 adapter 异步执行（外链 down 不阻塞业务）". If anchor
    enqueue raises (e.g. queue unavailable, asyncio loop conflict), we log a
    warning and swallow the exception so the surrounding transaction (mutation +
    persist + capability_call) still commits and ``emit_audit("after")`` still
    fires — same fail-soft semantics as the legacy ``_mutate`` path where
    anchor was the last step and any exception was effectively isolated to the
    caller's stack.

    Holds ``brain`` for ``_sync_database_aggregates`` (reads ``self._snapshot``);
    ``state_store`` + ``queue`` are explicit so ``pipeline_ops.enqueue_anchor``
    can take them directly.
    """
    def __init__(
        self,
        brain: Any,
        state_store: StateStore,
        queue: Any,
    ) -> None:
        self._brain = brain
        self._state_store = state_store
        self._queue = queue

    def __call__(self, pctx: PipelineContext, next_: NextFn) -> dict[str, Any]:
        result = next_(pctx)
        if pctx.is_write and pctx.skill.manifest.get("side_effects"):
            anchor_payload = pctx.payload | (result if isinstance(result, dict) else {"result": result})
            try:
                self._brain._sync_database_aggregates()
                pipeline_ops.enqueue_anchor(
                    self._queue, self._state_store,
                    pctx.audit_id, pctx.actor, pctx.skill.skill_id, anchor_payload,
                )
            except Exception as exc:  # noqa: BLE001 — D4 fail-soft contract
                import logging  # noqa: PLC0415
                logging.getLogger(__name__).warning(
                    "AnchorMiddleware: enqueue_anchor failed for skill=%s audit_id=%s err=%s",
                    pctx.skill.skill_id, pctx.audit_id, exc.__class__.__name__,
                )
        return result


# ───────────────────────────────────────────────────────────────────────────
# SkillPipeline — composes middlewares in the fixed order documented above.
# ───────────────────────────────────────────────────────────────────────────


# Module-level constant so preflight segment 42 can mechanically verify
# the order at static analysis time (no runtime introspection needed).
MIDDLEWARE_ORDER: tuple[str, ...] = (
    "CapabilityLogMiddleware",
    "PolicyMiddleware",
    "IdentityMiddleware",
    "AuditEmitMiddleware",
    "CapabilityCallMiddleware",
    "PersistMiddleware",
    "AnchorMiddleware",
)


@dataclass(frozen=True)
class SkillPipeline:
    """Ordered middleware chain executing a handler function.

    The chain is built once per HandlerDeps build (lazy-cached on
    BrainService). Middleware list is immutable; injecting a new
    cross-cutting requires rebuilding the pipeline (Action B does not yet
    expose a public ``insert_after``; Wave 2 cross-cuttings can request it).

    H3 fix — concurrency: the process-singleton ``BrainService._snapshot`` is a
    shared mutable dict that write handlers edit in place, and ``PersistMiddleware``
    then read-modify-writes the whole snapshot JSON into the single ``id=1``
    runtime-state row. Under ``ThreadingMixIn`` two concurrent writes would
    interleave "mutate snapshot → persist", so a request based on a stale
    snapshot could silently clobber another's committed change (last-writer-wins
    on requests list / audit feed / todos). ``_write_lock`` serializes the entire
    mutate→persist critical section at this single write choke point — every
    write path (``deps.write`` and ``pipeline_ops.run_mutation``) funnels through
    ``write`` below. The lock lives in the command/orchestration layer on purpose
    (the storage primitive ``database_store.save_runtime_state`` is intentionally
    left untouched). ``RLock`` (not ``Lock``) so a handler that re-enters the
    write path in-process — e.g. ``catalog.entry.create_draft`` → nested
    ``duplicate.check`` envelope — does not self-deadlock. Read path is unlocked:
    it neither mutates the snapshot nor persists.
    """
    middlewares: tuple[Middleware, ...]
    _write_lock: RLock = field(default_factory=RLock, repr=False, compare=False)

    def write(self, ctx: SkillContext, payload: dict[str, Any], fn: HandlerFn) -> dict[str, Any]:
        """Mutation path — runs all 6 middlewares under the write lock.

        Equivalent to legacy ``brain._mutate(ctx.skill_id, ctx.role, ctx.confirmed, payload, fn)``.

        ``fn(audit_id, actor)`` returns the handler-specific result dict;
        the pipeline wraps it with the standard envelope
        ``{"ok": True, "skill_id": ..., "audit_id": ..., "result": ...}``.

        H3: the lock spans the whole chain (handler mutate + PersistMiddleware
        sync_state_views + persist), so concurrent writes serialize instead of
        racing on the shared snapshot / id=1 runtime-state row.
        """
        with self._write_lock:
            pctx = PipelineContext(skill=ctx, payload=payload, is_write=True)
            result = self._invoke(pctx, fn)
            return {
                "ok": True,
                "skill_id": ctx.skill_id,
                "audit_id": pctx.audit_id,
                "result": result,
            }

    def read(self, ctx: SkillContext, payload: dict[str, Any], fn: HandlerFn) -> Any:
        """Read path — middleware chain without Persist + Anchor side-effects.

        Equivalent to legacy ``brain._invoke_traced_read(...)``. Returns the
        handler's raw result (not wrapped in an envelope — read skills set
        their own shape).
        """
        pctx = PipelineContext(skill=ctx, payload=payload, is_write=False)
        return self._invoke(pctx, fn)

    def _invoke(self, pctx: PipelineContext, fn: HandlerFn) -> Any:
        # innermost = the handler-provided function
        def innermost(p: PipelineContext) -> dict[str, Any]:
            return fn(p.audit_id, p.actor)

        chain: NextFn = innermost
        for mw in reversed(self.middlewares):
            chain = _bind(mw, chain)
        return chain(pctx)


def _bind(mw: Middleware, next_: NextFn) -> NextFn:
    """Helper to avoid loop-variable late-binding capture."""
    def wrapped(p: PipelineContext) -> dict[str, Any]:
        return mw(p, next_)
    return wrapped


# ───────────────────────────────────────────────────────────────────────────
# Factory — built once per BrainService at HandlerDeps construction.
# ───────────────────────────────────────────────────────────────────────────


def build_default_pipeline(brain: Any) -> SkillPipeline:
    """Construct the default 7-middleware chain bound to a BrainService.

    Action E: each middleware takes the minimum-viable dependency surface
    rather than a generic ``brain`` reference. ``audit_bus`` / ``queue`` /
    ``state_store`` / ``get_manifest`` are materialized here once; the
    decision-reason / target-ref resolvers default to ``pipeline_ops``
    canonical implementations (callers can swap via custom factory if
    needed for testing).
    """
    import zw_brain.shared.audit as audit_bus  # noqa: PLC0415
    from zw_brain.capability_registry.runtime import get_manifest  # noqa: PLC0415
    from zw_brain.shared import queue  # noqa: PLC0415

    return SkillPipeline(middlewares=(
        CapabilityLogMiddleware(),
        PolicyMiddleware(brain),
        IdentityMiddleware(brain),
        AuditEmitMiddleware(
            audit_bus,
            get_manifest,
            pipeline_ops.default_decision_reason,
            pipeline_ops.default_target_ref,
        ),
        CapabilityCallMiddleware(
            brain._state_store,
            pipeline_ops.default_target_ref,
        ),
        PersistMiddleware(brain),
        AnchorMiddleware(
            brain,
            brain._state_store,
            queue,
        ),
    ))
