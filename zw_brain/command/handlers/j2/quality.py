"""J2 quality handlers — 3 cap migrated from BrainService (F1 turn 4).

Method bodies physically migrated; `self.` → `brain.` substitution applied. Per-cap handler
functions registered in `zw_brain.command.dispatch.DISPATCH_TABLE`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from zw_brain.command.deps import HandlerDeps, SkillContext

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _upsert_quality_rule(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    rule_code = str(payload["rule_code"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        repo = deps.repos.metadata_evidence  # Action C — deps.repos always wired (DB or in-memory fallback)
        quality_ref = f"quality-rule:{rule_code}"
        evidence = repo.upsert_quality_evidence(
            {
                "quality_ref": quality_ref,
                "target_type": "quality_rule",
                "target_ref": rule_code,
                "quality_status": "active",
                "evidence_json": {
                    "rule_name": payload["rule_name"],
                    "rule_kind": payload["rule_kind"],
                    "rule_payload_json": payload.get("rule_payload_json") or {},
                    "target_catalog_codes": payload.get("target_catalog_codes") or [],
                    "issued_by": actor,
                    "issued_audit": audit_id,
                },
                "source_ref": f"orgmgr:rule:{rule_code}",
            }
        )
        deps.append_audit_feed("quality.rule.upsert", rule_code, "ok", actor)
        return {"rule_code": rule_code, "quality_ref": evidence.quality_ref, "audit_id": audit_id}

    return deps.write(ctx, payload, mutation)

def _run_quality_task(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    rule_code = str(payload["rule_code"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        repo = deps.repos.metadata_evidence  # Action C — deps.repos always wired (DB or in-memory fallback)
        task_ref = f"quality-task:{rule_code}:{audit_id[:8]}"
        repo.upsert_quality_evidence(
            {
                "quality_ref": task_ref,
                "target_type": "quality_task",
                "target_ref": rule_code,
                "quality_status": "running",
                "evidence_json": {
                    "target_catalog_code": payload.get("target_catalog_code"),
                    "scope_payload_json": payload.get("scope_payload_json") or {},
                    "issued_by": actor,
                    "issued_audit": audit_id,
                },
                "source_ref": f"orgmgr:task:{audit_id[:8]}",
            }
        )
        deps.append_audit_feed("quality.task.run", task_ref, "ok", actor)
        return {"task_ref": task_ref, "rule_code": rule_code, "task_status": "running", "audit_id": audit_id}

    return deps.write(ctx, payload, mutation)

def _replay_quality_task(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    rule_code = str(payload["rule_code"])
    previous_task_ref = str(payload["previous_task_ref"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        repo = deps.repos.metadata_evidence  # Action C — deps.repos always wired (DB or in-memory fallback)
        replay_ref = f"quality-task:{rule_code}:replay:{audit_id[:8]}"
        repo.upsert_quality_evidence(
            {
                "quality_ref": replay_ref,
                "target_type": "quality_task_replay",
                "target_ref": rule_code,
                "quality_status": "running",
                "evidence_json": {
                    "previous_task_ref": previous_task_ref,
                    "replay_reason": payload.get("reason"),
                    "issued_by": actor,
                    "issued_audit": audit_id,
                },
                "source_ref": f"orgmgr:replay:{audit_id[:8]}",
            }
        )
        deps.append_audit_feed("quality.task.replay", replay_ref, "ok", actor)
        return {"task_ref": replay_ref, "previous_task_ref": previous_task_ref, "audit_id": audit_id}

    return deps.write(ctx, payload, mutation)


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_quality_rule_upsert(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _upsert_quality_rule(brain, deps, ctx, payload)

def handler_quality_task_run(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _run_quality_task(brain, deps, ctx, payload)

def handler_quality_task_replay(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _replay_quality_task(brain, deps, ctx, payload)

