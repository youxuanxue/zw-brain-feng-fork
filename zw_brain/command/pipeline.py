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

    1. PolicyMiddleware         — enforce manifest policy + confirmation gate
    2. IdentityMiddleware       — resolve actor + mint audit_id, freeze into ctx
    3. AuditEmitMiddleware      — emit before/after/error audit events
    4. CapabilityCallMiddleware — append capability_call row to DB
    5. PersistMiddleware        — sync_state_views + persist (write-path only)
    6. AnchorMiddleware         — blockchain anchor outbox (side_effects only)

The chain has two entry shapes:

- ``pipeline.write(ctx, payload, fn)`` — full chain (mutation + persist + anchor)
- ``pipeline.read(ctx, payload, fn)`` — chain skipping Persist + Anchor (audit-only)

Each middleware delegates the actual operation to BrainService for now
(``brain_legacy._actor_for_role`` / ``_emit_audit`` / etc.); Action D
will lift those operations into proper domain services. The middleware
boundary is what stays stable across that work — handlers never see it.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from zw_brain.command.deps import SkillContext


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
# Concrete middlewares (each delegates the heavy lifting to BrainService for
# now; Action D will lift the operations into domain services / shared infra
# without changing the middleware boundary).
# ───────────────────────────────────────────────────────────────────────────


class PolicyMiddleware:
    """Enforce manifest policy + human_confirmation_required gate.

    Replaces the ``_enforce_manifest_policy(...) + ConfirmationRequiredError``
    block at the top of ``BrainService._mutate``. Read-only ``pipeline.read``
    path already had policy enforced by ``invoke_skill`` before dispatch, so
    this middleware short-circuits on ``not pctx.is_write``.
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
                from zw_brain.command.brain import ConfirmationRequiredError  # noqa: PLC0415
                raise ConfirmationRequiredError(pctx.skill.skill_id)
        return next_(pctx)


class IdentityMiddleware:
    """Resolve actor + mint audit_id; freeze into PipelineContext.

    Centralizes what was previously the first three lines of both _mutate
    and _invoke_traced_read::

        actor = self._actor_for_role(role)
        audit_id = ids.new_audit_id()
        started_at = datetime.now()
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
    the persist step. ``BrainService._emit_audit`` still owns the payload
    enrichment logic (10 branches: actor_snapshot / dev_iam_bypass / 5
    enrichment fields); this middleware only sequences the phase calls.
    """
    def __init__(self, brain: Any) -> None:
        self._brain = brain

    def __call__(self, pctx: PipelineContext, next_: NextFn) -> dict[str, Any]:
        self._brain._emit_audit(
            pctx.audit_id, pctx.actor, pctx.skill.skill_id, "before", pctx.payload,
        )
        try:
            result = next_(pctx)
        except Exception as exc:
            self._brain._emit_audit(
                pctx.audit_id, pctx.actor, pctx.skill.skill_id, "error",
                {"error": exc.__class__.__name__, "message": str(exc)},
            )
            raise
        # ``result`` may be a non-dict (read-only skills sometimes return list).
        after_payload = result if isinstance(result, dict) else {"result": result}
        self._brain._emit_audit(
            pctx.audit_id, pctx.actor, pctx.skill.skill_id, "after", after_payload,
        )
        return result


class CapabilityCallMiddleware:
    """Append the capability_call DB row (success or failed).

    Wraps next_() so that failure also records — replaces the explicit
    ``_record_capability_call(..., status="failed")`` in the except clause
    of _mutate / _invoke_traced_read.
    """
    def __init__(self, brain: Any) -> None:
        self._brain = brain

    def __call__(self, pctx: PipelineContext, next_: NextFn) -> dict[str, Any]:
        try:
            result = next_(pctx)
        except Exception as exc:
            self._brain._record_capability_call(
                pctx.audit_id, pctx.actor, pctx.skill.role, pctx.skill.skill_id,
                pctx.payload,
                {"error": exc.__class__.__name__, "message": str(exc)},
                pctx.started_at, status="failed",
            )
            raise
        record_payload = result if isinstance(result, dict) else {"result": result}
        self._brain._record_capability_call(
            pctx.audit_id, pctx.actor, pctx.skill.role, pctx.skill.skill_id,
            pctx.payload, record_payload, pctx.started_at,
        )
        return result


class PersistMiddleware:
    """``sync_state_views`` + ``persist`` after a successful mutation.

    Read path skips this middleware entirely (no snapshot changes to persist).
    """
    def __init__(self, brain: Any) -> None:
        self._brain = brain

    def __call__(self, pctx: PipelineContext, next_: NextFn) -> dict[str, Any]:
        result = next_(pctx)
        if pctx.is_write:
            self._brain._sync_state_views()
            self._brain._persist()
        return result


class AnchorMiddleware:
    """Sync database aggregates + enqueue blockchain anchor for ``side_effects`` skills.

    Mutation-only and side-effects-only — both read path and non-side-effect
    writes skip the heavy lifting.

    Fail-soft per docs/approved/zw-brain-architecture.md D4: "审计总线强制同步落库；
    区块链锚定通过可插拔 adapter 异步执行（外链 down 不阻塞业务）". If ``_enqueue_anchor``
    raises (e.g. queue unavailable, asyncio loop conflict), we log a warning and
    swallow the exception so the surrounding transaction (mutation + persist +
    capability_call) still commits and ``emit_audit("after")`` still fires —
    same fail-soft semantics as the legacy ``_mutate`` path where anchor was the
    last step and any exception was effectively isolated to the caller's stack.
    """
    def __init__(self, brain: Any) -> None:
        self._brain = brain

    def __call__(self, pctx: PipelineContext, next_: NextFn) -> dict[str, Any]:
        result = next_(pctx)
        if pctx.is_write and pctx.skill.manifest.get("side_effects"):
            anchor_payload = pctx.payload | (result if isinstance(result, dict) else {"result": result})
            try:
                self._brain._sync_database_aggregates()
                self._brain._enqueue_anchor(
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
    """
    middlewares: tuple[Middleware, ...]

    def write(self, ctx: SkillContext, payload: dict[str, Any], fn: HandlerFn) -> dict[str, Any]:
        """Mutation path — runs all 6 middlewares.

        Equivalent to legacy ``brain._mutate(ctx.skill_id, ctx.role, ctx.confirmed, payload, fn)``.

        ``fn(audit_id, actor)`` returns the handler-specific result dict;
        the pipeline wraps it with the standard envelope
        ``{"ok": True, "skill_id": ..., "audit_id": ..., "result": ...}``.
        """
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
    """Construct the default 6-middleware chain bound to a BrainService.

    The fixed order matches ``MIDDLEWARE_ORDER`` and is verified by preflight
    segment 41. ``brain`` is passed positionally to each middleware; Action D
    will replace this with explicit domain service injection.
    """
    return SkillPipeline(middlewares=(
        PolicyMiddleware(brain),
        IdentityMiddleware(brain),
        AuditEmitMiddleware(brain),
        CapabilityCallMiddleware(brain),
        PersistMiddleware(brain),
        AnchorMiddleware(brain),
    ))
