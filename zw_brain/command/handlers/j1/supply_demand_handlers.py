"""J1 supply-demand browser handlers — demand.register / demand.phase.advance / demand.list."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

import zw_brain.shared.clock as clock
from zw_brain.command.brain import InvalidStateError, NotFoundError
from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.domain.repositories.supply_demand import SupplyDemandRepository
from zw_brain.domain.supply_demand_phase import SupplyDemandPhaseError
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID


def _repo() -> SupplyDemandRepository:
    return SupplyDemandRepository()


def handler_demand_register(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        demand_id = str(payload.get("demand_id") or f"DM-{clock.now_datetime().replace(' ', '-').replace(':', '')}")
        record = _repo().register_demand(
            demand_id=demand_id,
            title=str(payload["title"]),
            applicant=str(payload.get("applicant") or actor),
            applicant_dept=str(payload.get("applicant_dept") or "申请部门"),
            tenant_id=_DEFAULT_TENANT_ID,
            target_resource_hint=payload.get("target_resource_hint"),
        )
        deps.append_audit_feed("demand.register", demand_id, "ok", actor)
        return record | {"audit_id": audit_id}

    return deps.write(ctx, payload, mutation)


def handler_demand_phase_advance(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    demand_id = str(payload["demand_id"])
    next_phase = str(payload["next_phase"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        try:
            record = _repo().advance_phase(demand_id, next_phase, tenant_id=_DEFAULT_TENANT_ID)
        except KeyError as exc:
            raise NotFoundError(demand_id) from exc
        except SupplyDemandPhaseError as exc:
            raise InvalidStateError(str(exc)) from exc
        deps.append_audit_feed("demand.phase.advance", demand_id, "ok", actor)
        return record | {"audit_id": audit_id}

    return deps.write(ctx, {"demand_id": demand_id, "next_phase": next_phase} | payload, mutation)


def handler_demand_list(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    phase = payload.get("phase")
    items = _repo().list_demands(
        tenant_id=_DEFAULT_TENANT_ID,
        phase=str(phase) if phase else None,
    )
    return {"items": items, "total": len(items)}
