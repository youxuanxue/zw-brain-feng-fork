"""Test invocation helper — bridge old handler(brain, skill_id, payload) call sites
to the new handler(deps, ctx, payload) signature (Action A, 2026-05-27).

Most integration / unit tests should use ``invoke_trusted`` (tests/_trusted_payload.py)
which goes through ``brain.invoke_skill`` and exercises the full pipeline.

A small set of tests call handlers directly with ``brain=None`` to bypass the
pipeline (audit query / replay handlers use ``audit_index`` module directly and
don't dereference ``brain``). For those, this helper constructs the
``deps`` / ``ctx`` arguments the handler now expects.

Usage::

    # OLD: handler_X(brain=B, skill_id="X.skill", payload={...})
    # NEW: call_handler(handler_X, brain=B, skill_id="X.skill", payload={...})

When ``brain is None``, ``deps`` is None and ``ctx`` has an empty manifest —
sufficient for the audit-query family of handlers that don't reach into
``deps.brain_legacy``. Handlers that DO need brain access will fail loud here,
which is the intended signal to migrate the test to ``invoke_trusted``.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from zw_brain.command.deps import HandlerDeps, SkillContext


def call_handler(
    handler_fn: Callable[..., Any],
    *,
    brain: Any = None,
    skill_id: str,
    payload: dict[str, Any] | None = None,
    role: str = "ROLE_ORGAN_OPERATER",
) -> Any:
    payload = payload or {}
    if brain is not None:
        deps: HandlerDeps | None = brain._get_handler_deps()
        manifest = brain.manifests().get(skill_id, {})
        actor = brain._actor_for_role(role) if role else ""
    else:
        deps = None
        manifest = {}
        actor = ""
    ctx = SkillContext(
        skill_id=skill_id,
        role=role,
        actor=actor,
        confirmed=bool(payload.get("confirmed")),
        manifest=manifest,
    )
    return handler_fn(deps, ctx, payload)
