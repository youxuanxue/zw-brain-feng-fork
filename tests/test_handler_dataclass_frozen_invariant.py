"""Invariant test — handler-facing dataclasses must be frozen.

PR #128 (R-002) established that HandlerDeps / SkillContext / Repos are the
process-wide / per-call **public** dependency container; making them
``@dataclass(frozen=True)`` prevents accidental field reassignment in
handler code (which would break the "stable container" promise).

This test catches regressions: if a future PR drops ``frozen=True`` on any
of the three public dataclasses, this test fails. The mutable
``PipelineContext`` in ``zw_brain/command/pipeline.py`` is explicitly NOT
in this list — it's an internal middleware scratchpad.
"""
from __future__ import annotations

from zw_brain.command.deps import HandlerDeps, Repos, SkillContext


def test_handler_deps_frozen() -> None:
    assert HandlerDeps.__dataclass_params__.frozen, (
        "HandlerDeps must be @dataclass(frozen=True) — accidental reassignment "
        "of fields (deps.repos / deps.pipeline / deps.brain_legacy) breaks the "
        "process-wide stability contract relied on by all 199 handlers."
    )


def test_skill_context_frozen() -> None:
    assert SkillContext.__dataclass_params__.frozen, (
        "SkillContext must be @dataclass(frozen=True) — per-call identity "
        "(skill_id / role / actor / confirmed / manifest) must not mutate "
        "after invoke_skill builds it."
    )


def test_repos_frozen() -> None:
    assert Repos.__dataclass_params__.frozen, (
        "Repos must be @dataclass(frozen=True) — the 6 repo handles bind "
        "to a single BrainService at construction time; reassigning them "
        "would silently change which DB store handlers talk to."
    )
