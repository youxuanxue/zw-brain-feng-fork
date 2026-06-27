"""J1 supply-demand browser handlers — demand.register / demand.response.submit / demand.close / demand.list."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

import zw_brain.shared.clock as clock
from zw_brain.command.brain import InvalidStateError, NotFoundError
from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.domain.repositories.supply_demand import SupplyDemandRepository
from zw_brain.domain.supply_demand_status import SupplyDemandStatusError
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
            target_org_code=payload.get("target_org_code"),
            target_org_name=payload.get("target_org_name"),
        )
        deps.append_audit_feed("demand.register", demand_id, "ok", actor)
        return record | {"audit_id": audit_id}

    return deps.write(ctx, payload, mutation)


def handler_demand_response_submit(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    demand_id = str(payload["demand_id"])
    decision = str(payload["decision"])
    response_note = str(payload["response_note"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        try:
            record = _repo().submit_response(
                demand_id,
                tenant_id=_DEFAULT_TENANT_ID,
                decision=decision,
                response_note=response_note,
                resource_ref=payload.get("resource_ref"),
                responded_by=actor,
            )
        except KeyError as exc:
            raise NotFoundError(demand_id) from exc
        except (SupplyDemandStatusError, ValueError) as exc:
            raise InvalidStateError(str(exc)) from exc
        deps.append_audit_feed("demand.response.submit", demand_id, "ok", actor)
        return record | {"audit_id": audit_id}

    return deps.write(ctx, {"demand_id": demand_id, "decision": decision, "response_note": response_note} | payload, mutation)


def handler_demand_close(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    demand_id = str(payload["demand_id"])
    close_note = str(payload.get("close_note") or "")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        try:
            record = _repo().close_demand(
                demand_id,
                tenant_id=_DEFAULT_TENANT_ID,
                close_note=close_note,
                closed_by=actor,
            )
        except KeyError as exc:
            raise NotFoundError(demand_id) from exc
        except SupplyDemandStatusError as exc:
            raise InvalidStateError(str(exc)) from exc
        deps.append_audit_feed("demand.close", demand_id, "ok", actor)
        return record | {"audit_id": audit_id}

    return deps.write(ctx, {"demand_id": demand_id, "close_note": close_note} | payload, mutation)


def handler_demand_list(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    response_status = payload.get("response_status")
    items = _repo().list_demands(
        tenant_id=_DEFAULT_TENANT_ID,
        response_status=str(response_status) if response_status else None,
    )
    return {"items": items, "total": len(items)}
