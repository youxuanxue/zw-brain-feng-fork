"""J1 requirement_intake handlers — 9 cap migrated from BrainService (F1 turn 6, J1 收官)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

import copy

import zw_brain.shared.clock as clock
from zw_brain.command.brain import DEFAULT_DISCOVERY_QUERY, InvalidStateError, NotFoundError
from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID
from zw_brain.shared.sanitization import safe_json

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _submit_requirement_intent(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    return brain.create_request(str(payload.get("resource_id") or "res-jbxx-ledger"), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")), str(payload.get("intent") or payload.get("title") or DEFAULT_DISCOVERY_QUERY), "require.intent.submit")

def _refine_requirement_intent(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    request_id = str(payload["request_id"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        request = deps.view.requests.find_by_id(request_id)
        request.setdefault("timeline", []).append({"label": "需求已细化", "time": clock.now_datetime(), "note": str(payload.get("refine_note", "已补充需求意图与资源范围。"))})
        request["purpose"] = str(payload.get("refine_note") or request.get("purpose"))
        request["aiStatus"]["summary"] = "需求意图已细化，仍保持受控准入链路。"
        deps.append_audit_feed("require.intent.refine", request_id, "ok", actor)
        return {"request_id": request_id, "status": request["status"], "audit_id": audit_id}

    return deps.write(ctx, payload, mutation)

def _review_requirement_intent(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    return brain.review_request(str(payload["request_id"]), str(payload["decision"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")), "require.intent.review")

def _dispatch_require_resource(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    application_code = str(payload["application_code"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        from sqlalchemy import select  # noqa: PLC0415

        from zw_brain.domain.models import ApplicationRecord  # noqa: PLC0415
        from zw_brain.shared.db import create_session_factory  # noqa: PLC0415

        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            rec = session.execute(
                select(ApplicationRecord)
                .where(ApplicationRecord.tenant_id == _DEFAULT_TENANT_ID)
                .where(ApplicationRecord.application_code == application_code)
            ).scalar_one_or_none()
            if rec is None:
                raise NotFoundError(application_code)
            merged = copy.deepcopy(rec.payload_json or {})
            merged["dispatch_payload"] = payload.get("dispatch_payload_json") or {}
            merged["dispatch_target_region_codes"] = payload.get("target_region_codes") or []
            merged["dispatched_by_audit"] = audit_id
            rec.payload_json = merged
            rec.status = "dispatched"
            session.commit()
        deps.append_audit_feed("require.resource.dispatch", application_code, "ok", actor)
        return {"application_code": application_code, "status": "dispatched", "audit_id": audit_id}

    return deps.write(ctx, payload, mutation)

def _match_requirement_resource(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    request_id = str(payload["request_id"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        request = deps.view.requests.find_by_id(request_id)
        candidates = payload.get("candidate_resources") or ([payload["resource_id"]] if payload.get("resource_id") else [])
        request["matchedResources"] = safe_json(candidates)
        request.setdefault("timeline", []).append({"label": "资源匹配完成", "time": clock.now_datetime(), "note": str(payload.get("match_note", "已生成候选资源匹配结果。"))})
        deps.append_audit_feed("require.resource.match", request_id, "ok", actor)
        return {"request_id": request_id, "candidate_count": len(candidates), "audit_id": audit_id}

    return deps.write(ctx, payload, mutation)

def _handoff_require_task(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    application_code = str(payload["application_code"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        handoff = {
            "application_code": application_code,
            "handoff_to_role": payload["handoff_to_role"],
            "handoff_note": payload.get("handoff_note"),
            "actor": actor,
        }
        deps.append_audit_feed("require.task.handoff", application_code, "ok", actor)
        return handoff | {"audit_id": audit_id}

    return deps.write(ctx, payload, mutation)

def _submit_supplement(brain, deps, ctx, request_id: str, role: str, confirmed: bool) -> dict[str, Any]:
    request = deps.view.requests.find_by_id(request_id)
    if request["status"] != "supplementing":
        raise InvalidStateError("request is not in supplementing state")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        request["status"] = "summary-pending"
        request["diffFields"] = [
            {"label": "经营状态", "value": "正常经营", "reason": "现场状态变化快", "owner": "基层填报人 补录", "state": "已补录"},
            {"label": "最近走访时间", "value": clock.now_date(), "reason": "共享池无现场时间", "owner": "村社区填报人 补录", "state": "已补录"},
            {"label": "现场备注", "value": "已完成走访核验，无新增异常。", "reason": "仅末端掌握", "owner": "基层填报人 补录", "state": "已补录"},
        ]
        request["summaryResult"]["note"] = "基层差异字段已全部回收，系统已生成自动汇总结果，待 审核汇总人 确认异常项。"
        request["timeline"].append(
            {
                "label": "差异补录已提交",
                "time": clock.now_datetime(),
                "note": "基层已提交现场差异字段，系统已自动进入汇总确认阶段。",
            }
        )
        request["aiStatus"]["summary"] = "差异补录已提交，系统已完成自动汇总并等待 审核汇总人 处理异常项。"
        request["aiStatus"]["nextAction"] = "请 审核汇总人 查看自动汇总结果并确认异常项。"
        delivery = deps.view.delivery.find_by_request_id(request_id)
        if delivery:
            delivery["status"] = "reconciling"
            delivery["updatedAt"] = clock.now_datetime()
            delivery["note"] = "基层补录已完成，自动汇总结果待审核汇总人员确认。"
            delivery["history"].append(
                {
                    "time": clock.now_short_time(),
                    "state": "基层补录完成",
                    "detail": "差异字段已回收，系统已生成汇总草稿和回流候选。",
                }
            )
            delivery["aiSummary"]["summary"] = "链路已进入“自动汇总 → 异常确认 → 回流候选”阶段。"
            delivery["aiSummary"]["nextAction"] = "请 审核汇总人 确认异常项，再由 数据提供方 / 业务运营员 决定是否纳入模板。"
            delivery["aiSummary"]["cause"] = "基层只补差异字段，因此系统可直接生成汇总结果。"
            delivery["aiSummary"]["impact"] = "确认完成后可把高频差异字段推进到模板治理侧。"
            delivery["backflow"]["status"] = "待确认"
            delivery["backflow"]["note"] = "差异字段已具备来源与责任方，待汇总确认后进入供给侧确认。"
        deps.append_audit_feed("supplement.submit", request_id, "ok", actor)
        return {"request_id": request_id, "status": request["status"]}

    return deps.write(ctx, {"request_id": request_id}, mutation)

def _confirm_summary(brain, deps, ctx, request_id: str, role: str, confirmed: bool) -> dict[str, Any]:
    request = deps.view.requests.find_by_id(request_id)
    if request["status"] != "summary-pending":
        raise InvalidStateError("request is not ready for summary confirmation")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        request["status"] = "completed"
        request["summaryResult"]["note"] = "审核汇总人 已确认自动汇总结果，链路进入回流候选确认。"
        request["timeline"].append(
            {
                "label": "已确认自动汇总",
                "time": clock.now_datetime(),
                "note": "异常项已处理完成，回流候选进入供给侧确认阶段。",
            }
        )
        request["aiStatus"]["summary"] = "自动汇总已确认，当前只剩回流候选是否正式纳入模板。"
        request["aiStatus"]["nextAction"] = "请数据提供方 / 业务运营员确认这批高频字段是否纳入目录，并更新对应的填报模板。"
        delivery = deps.view.delivery.find_by_request_id(request_id)
        if delivery:
            delivery["status"] = "reconciling"
            delivery["updatedAt"] = clock.now_datetime()
            delivery["note"] = "汇总已确认，等待 数据提供方 / 业务运营员 决定回流是否正式生效。"
            delivery["history"].append(
                {
                    "time": clock.now_short_time(),
                    "state": "汇总确认完成",
                    "detail": "异常项已由 审核汇总人 确认，任务转入回流确认。",
                }
            )
            delivery["aiSummary"]["summary"] = "业务汇总已经闭环，当前重心转到模板治理和回流生效。"
            delivery["aiSummary"]["nextAction"] = "请确认是否把本地泊位开放状态和最新开放时间纳入停车场信息目录回流候选。"
            delivery["aiSummary"]["cause"] = "自动汇总结果已被人工确认，可进入供给侧治理动作。"
            delivery["aiSummary"]["impact"] = "回流确认后，下次类似需求的基层补录字段会进一步下降。"
            delivery["backflow"]["status"] = "待确认"
            delivery["backflow"]["note"] = "回流候选已具备业务证据，待台账管理员与目录管理员确认。"
            delivery["summaryConfirmed"] = True
        deps.append_audit_feed("summary.confirm", request_id, "ok", actor)
        return {"request_id": request_id, "status": request["status"]}

    return deps.write(ctx, {"request_id": request_id}, mutation)

def _confirm_backflow(brain, deps, ctx, task_id: str, role: str, confirmed: bool) -> dict[str, Any]:
    task = deps.view.delivery.find_by_id(task_id)
    request = deps.view.requests.find_by_id(task["requestId"])
    if request["status"] != "completed" or task.get("receiptStatus") != "reconciled" or task["backflow"]["status"] == "已确认":
        raise InvalidStateError("delivery task is not ready for backflow confirmation")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        task["status"] = "completed"
        task["updatedAt"] = clock.now_datetime()
        task["note"] = "高频差异字段已确认纳入停车场信息共享目录回流候选。"
        task["history"].append(
            {
                "time": clock.now_short_time(),
                "state": "回流确认完成",
                "detail": "本地泊位开放状态与最新开放时间已正式纳入停车场信息目录回流候选。",
            }
        )
        task["aiSummary"]["summary"] = "这条链路已经从一次性补录沉淀成下一次可直接复用的模板能力。"
        task["aiSummary"]["nextAction"] = "请到“维护数据供给”和“专题包”里确认填报模板和目录归集是否已更新到位。"
        task["aiSummary"]["cause"] = "高频差异字段已经过一次真实业务验证，并具备明确来源与责任方。"
        task["aiSummary"]["impact"] = "下次类似需求将进一步减少基层补录工作量。"
        task["backflow"]["status"] = "已确认"
        task["backflow"]["note"] = "本地泊位开放状态、最新开放时间已纳入停车场信息目录回流候选。"
        deps.append_audit_feed("backflow.confirm", task["backflow"]["candidateObject"], "ok", actor)
        return {"task_id": task_id, "status": task["status"]}

    return deps.write(ctx, {"task_id": task_id}, mutation)


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_require_intent_submit(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _submit_requirement_intent(brain, deps, ctx, payload)

def handler_require_intent_refine(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _refine_requirement_intent(brain, deps, ctx, payload)

def handler_require_intent_review(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _review_requirement_intent(brain, deps, ctx, payload)

def handler_require_resource_dispatch(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _dispatch_require_resource(brain, deps, ctx, payload)

def handler_require_resource_match(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _match_requirement_resource(brain, deps, ctx, payload)

def handler_require_task_handoff(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _handoff_require_task(brain, deps, ctx, payload)

def handler_supplement_submit(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _submit_supplement(brain, deps, ctx, str(payload["request_id"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))

def handler_summary_confirm(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _confirm_summary(brain, deps, ctx, str(payload["request_id"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))

def handler_backflow_confirm(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _confirm_backflow(brain, deps, ctx, str(payload["task_id"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))

