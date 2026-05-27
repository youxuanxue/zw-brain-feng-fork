"""J1 delivery handlers — 12 cap migrated from BrainService (F1 turn 6, J1 收官)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

import copy

import zw_brain.shared.clock as clock
from zw_brain.command.brain import BrainServiceError, InvalidStateError, NotFoundError, _mask
from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEFAULT_TENANT_ID = get_runtime_tenant_id()


# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _plan_delivery_exchange(brain, payload: dict[str, Any]) -> dict[str, Any]:
    return brain._record_delivery_attempt(payload, "delivery.exchange.plan", "planned", "plan")

def _publish_delivery_exchange(brain, payload: dict[str, Any]) -> dict[str, Any]:
    return brain._record_delivery_attempt(payload, "delivery.exchange.publish", "published", "publish")

def _start_delivery_exchange(brain, payload: dict[str, Any]) -> dict[str, Any]:
    return brain._record_delivery_attempt(payload, "delivery.exchange.start", "running", "exchange")

def _stop_delivery_exchange(brain, payload: dict[str, Any]) -> dict[str, Any]:
    return brain._record_delivery_attempt(payload, "delivery.exchange.stop", "stopped", "stop")

def _ingest_delivery_receipt(brain, payload: dict[str, Any]) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    task_id = str(payload["task_id"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        task = brain._maybe_delivery(task_id)
        if task is not None:
            task["receiptStatus"] = str(payload["receipt_status"])
            task["receiptNo"] = payload.get("receipt", {}).get("receipt_no") or payload.get("receipt_no") or task.get("receiptNo")
            task["updatedAt"] = clock.now_datetime()
            task.setdefault("history", []).append({"time": clock.now_short_time(), "state": "回执已接收", "detail": f"交付回执状态：{payload['receipt_status']}。"})
        receipt = deps.repos.delivery.append_receipt(
            {
                "delivery_code": task_id,
                "receipt_type": "exchange",
                "receipt_no": payload.get("receipt", {}).get("receipt_no") or payload.get("receipt_no"),
                "receipt_status": payload["receipt_status"],
                "payload_json": payload.get("receipt") or {},
            }
        )
        if payload.get("attempt_id"):
            deps.repos.delivery.add_execution_evidence(
                {
                    "evidence_ref": audit_id,
                    "delivery_code": task_id,
                    "attempt_code": payload.get("attempt_id"),
                    "executor_kind": "exchange_receipt",
                    "evidence_kind": "delivery_receipt",
                    "result_status": payload["receipt_status"],
                    "payload_json": payload.get("receipt") or payload,
                }
            )
        if isinstance(payload.get("metrics"), dict):
            deps.repos.delivery.upsert_exchange_metric(payload["metrics"] | {"delivery_code": task_id, "status": payload["receipt_status"]})
        brain._append_audit_feed("delivery.receipt.ingest", task_id, "ok", actor)
        return {"task_id": task_id, "receipt_status": receipt.receipt_status, "receipt_id": receipt.id, "audit_id": audit_id}

    return brain._mutate("delivery.receipt.ingest", role, confirmed, payload, mutation)

def _reconcile_delivery_receipt(brain, task_id: str, role: str, confirmed: bool) -> dict[str, Any]:
    task = brain._delivery_by_id(task_id)
    if task["status"] == "failed":
        raise InvalidStateError("failed delivery task cannot be reconciled without recovery")
    if task.get("receiptStatus") == "reconciled":
        raise InvalidStateError("delivery receipt is already reconciled")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        task["receiptStatus"] = "reconciled"
        task["receiptNo"] = f"RCPT-{task_id.split('-')[-1]}"
        task["updatedAt"] = clock.now_datetime()
        task["note"] = "交付回执已对账确认，当前可继续等待回流或治理动作。"
        task["history"].append(
            {
                "time": clock.now_short_time(),
                "state": "回执已对账",
                "detail": "平台已完成交付回执核对并保留审计留痕。",
            }
        )
        task["aiSummary"]["summary"] = "交付回执已完成对账，当前链路事实与外部回执保持一致。"
        task["aiSummary"]["nextAction"] = "如已满足业务门槛，可继续执行回流确认或供给侧治理动作。"
        brain._append_audit_feed("delivery.reconcile-receipt", task_id, "ok", actor)
        return {"task_id": task_id, "receipt_status": task["receiptStatus"]}

    return brain._mutate("delivery.reconcile_receipt", role, confirmed, {"task_id": task_id}, mutation)

def _replace_or_cancel_delivery(brain, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    delivery_code = str(payload["delivery_code"])
    action = str(payload["action"])
    if action not in {"replace", "cancel"}:
        raise BrainServiceError(f"unsupported delivery.replace_or_cancel action: {action}")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        from sqlalchemy import select  # noqa: PLC0415

        from zw_brain.domain.models import DeliveryTaskRecord  # noqa: PLC0415
        from zw_brain.shared.db import create_session_factory  # noqa: PLC0415

        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            rec = session.execute(
                select(DeliveryTaskRecord)
                .where(DeliveryTaskRecord.tenant_id == _DEFAULT_TENANT_ID)
                .where(DeliveryTaskRecord.delivery_code == delivery_code)
            ).scalar_one_or_none()
            if rec is None:
                raise NotFoundError(delivery_code)
            merged = copy.deepcopy(rec.payload_json or {})
            merged["withdrawal_handling"] = {
                "action": action,
                "replacement_resource_id": payload.get("replacement_resource_id"),
                "reason": payload.get("reason"),
                "audit_id": audit_id,
            }
            rec.payload_json = merged
            new_state = "replaced" if action == "replace" else "cancelled"
            rec.state = new_state
            session.commit()
        brain._append_audit_feed("delivery.replace_or_cancel", delivery_code, "ok", actor)
        return {"delivery_code": delivery_code, "action": action, "state": new_state, "audit_id": audit_id}

    return brain._mutate("delivery.replace_or_cancel", role, confirmed, payload, mutation)

def _manage_delivery_subscription(brain, payload: dict[str, Any]) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    action = str(payload["action"])
    if action not in {"create", "activate", "pause", "resume", "cancel"}:
        raise InvalidStateError(f"unsupported subscription action: {action}")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        task = brain._delivery_by_id(str(payload["task_id"]))
        status = {"create": "active", "activate": "active", "pause": "paused", "resume": "active", "cancel": "cancelled"}[action]
        subscription = deps.repos.delivery.upsert_subscription({"subscription_code": payload.get("subscription_id"), "delivery_code": task["id"], "resource_code": task.get("resourceId") or task.get("access", {}).get("resource_code"), "status": status, "schedule_ref": payload.get("schedule_ref") or {}, "policy_snapshot": payload.get("policy_snapshot") or {}, "legacy_status_snapshot": {"action": action, "task_status": task.get("status")}})
        task.setdefault("history", []).append({"time": clock.now_short_time(), "state": "订阅策略已更新", "detail": f"订阅状态：{status}"})
        brain._append_audit_feed("delivery.subscription.manage", task["id"], "ok", actor)
        return {"subscription_code": subscription.subscription_code, "status": subscription.status, "audit_id": audit_id}

    return brain._mutate("delivery.subscription.manage", role, confirmed, payload, mutation)

def _trigger_delivery_recovery(brain, task_id: str, role: str, confirmed: bool) -> dict[str, Any]:
    task = brain._delivery_by_id(task_id)
    if task["status"] != "failed":
        raise InvalidStateError("delivery task is not in failed state")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        task["status"] = "warning"
        task["updatedAt"] = clock.now_datetime()
        task["note"] = "已触发恢复流程，等待审计链修复后重新对账。"
        task["history"].append(
            {
                "time": clock.now_short_time(),
                "state": "恢复已触发",
                "detail": "平台已显式登记恢复动作，等待后续重试与回执。",
            }
        )
        task["aiSummary"]["summary"] = "恢复动作已被显式触发，当前任务从失败态回到可追踪处理中间态。"
        task["aiSummary"]["nextAction"] = "请先修复审计链路，再重新执行补投和回执对账。"
        brain._append_audit_feed("delivery.trigger-recovery", task_id, "ok", actor)
        return {"task_id": task_id, "status": task["status"]}

    return brain._mutate("delivery.trigger_recovery", role, confirmed, {"task_id": task_id}, mutation)

def _get_delivery_task(brain, task_id: str) -> dict[str, Any]:
    store = brain._state_store.database_store
    task = brain._maybe_delivery(task_id)
    if task is None:
        if store is None:
            raise NotFoundError(task_id)
        task = brain._delivery_task_from_record(task_id, store)
        if task is None:
            raise NotFoundError(task_id)
    else:
        task = copy.deepcopy(task)
    if store is None:
        return task
    record = next((item for item in store.delivery_repo.list_tasks(tenant_id=_DEFAULT_TENANT_ID) if item.delivery_code == task_id), None)
    request = brain._maybe_request(task.get("requestId", "")) or brain._request_from_application_record(task.get("requestId", ""), store)
    if request is not None:
        task["applicationMaterials"] = copy.deepcopy(request.get("applicationMaterials", {}))
        task["applicationMaterials"].setdefault("frequency", {"times": "", "mostTimes": "", "timeWindow": None, "useDays": ""})
        task["statusTimeline"] = brain._request_status_timeline(request, task)
        task["schemaEvidence"] = {
            "fieldBindingSummary": copy.deepcopy(request.get("fieldBindingSummary", {})),
            "fieldBindings": copy.deepcopy(request.get("fieldBindings", [])),
            "schemaSnapshots": copy.deepcopy(request.get("schemaSnapshots", [])),
            "qualityEvidence": copy.deepcopy(request.get("qualityEvidence", {})),
        }
    if record is not None:
        task["status"] = record.state
        task["repository"] = {
            "delivery_code": record.delivery_code,
            "application_code": record.application_code,
            "channel": record.channel,
        }
        payload = record.payload_json or {}
        task["accessGrantSnapshot"] = _mask(copy.deepcopy(payload.get("access_grant") or {}))
        task["authorizationBoundary"] = brain._authorization_boundary(task["accessGrantSnapshot"])
        task["r2Review"] = _mask(copy.deepcopy(payload.get("r2_review") or {}))
        task["grantBoundary"] = _mask(copy.deepcopy(payload.get("grant_boundary") or {}))
        task["supplementBoundary"] = _mask(copy.deepcopy(payload.get("supplement_boundary") or {}))
        task["nonGrantBoundary"] = _mask(copy.deepcopy(payload.get("non_grant_boundary") or {}))
        task["renewalBoundary"] = payload.get("renewal_boundary") or "真实 data_apply_renewal 无行；不伪造续期成功路径。"
        task["legacyMappings"] = brain._legacy_mapping_refs(store, "DeliveryTaskRecord", record.delivery_code)
        task["receipts"] = [
            {
                "receiptType": item.receipt_type,
                "receiptNo": item.receipt_no,
                "receiptStatus": item.receipt_status,
                "payload": copy.deepcopy(item.payload_json),
            }
            for item in store.delivery_repo.list_receipts(task_id)
        ]
        if task["receipts"]:
            task["receiptStatus"] = task["receipts"][-1]["receiptStatus"]
            task["receiptNo"] = task["receipts"][-1]["receiptNo"]
    return task


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_delivery_exchange_plan(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _plan_delivery_exchange(brain, payload)

def handler_delivery_exchange_publish(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _publish_delivery_exchange(brain, payload)

def handler_delivery_exchange_start(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _start_delivery_exchange(brain, payload)

def handler_delivery_exchange_stop(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _stop_delivery_exchange(brain, payload)

def handler_delivery_receipt_ingest(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _ingest_delivery_receipt(brain, payload)

def handler_delivery_reconcile_receipt(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _reconcile_delivery_receipt(brain, str(payload["task_id"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))

def handler_delivery_replace_or_cancel(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _replace_or_cancel_delivery(brain, payload)

def handler_delivery_subscription_manage(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _manage_delivery_subscription(brain, payload)

def handler_delivery_trigger_recovery(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _trigger_delivery_recovery(brain, str(payload["task_id"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))

def handler_delivery_view(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _get_delivery_task(brain, str(payload["task_id"]))

def handler_delivery_access_grant(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return brain.grant_delivery_access(str(payload["task_id"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))

def handler_delivery_list(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return {"items": brain.list_delivery_tasks()}

